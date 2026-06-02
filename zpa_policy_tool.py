#!/usr/bin/env python3
"""CLI for inspecting and updating ZPA policy rules."""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ONEAPI_BASE_URL = "https://api.zsapi.net"
DEFAULT_LEGACY_ZPA_BASE_URL = "https://config.private.zscaler.com"
DEFAULT_AUDIENCE = "https://api.zscaler.com"
DEFAULT_POLICY_TYPE = "ACCESS_POLICY"
AUTH_MODES = ("legacy", "oneapi")


class CliError(Exception):
    """Expected user-facing error."""


class ApiError(CliError):
    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"{method} {url} failed with HTTP {status}: {body}")


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def require_env(name: str) -> str:
    value = env(name)
    if value is None:
        raise CliError(f"Missing required environment variable: {name}")
    return value


def strip_slash(value: str) -> str:
    return value.rstrip("/")


def normalize_auth_mode(value: str | None) -> str:
    mode = (value or "legacy").strip().casefold()
    if mode not in AUTH_MODES:
        raise CliError(f"Unsupported auth mode {value!r}. Expected one of: {', '.join(AUTH_MODES)}")
    return mode


def add_query(path: str, query: dict[str, Any] | None) -> str:
    if not query:
        return path
    clean = {key: value for key, value in query.items() if value is not None}
    if not clean:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urllib.parse.urlencode(clean)}"


def load_json(data: bytes) -> Any:
    if not data:
        return {}
    text = data.decode("utf-8")
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def print_json(value: Any) -> None:
    print(dump_json(value))


def normalize_name(value: Any) -> str:
    return "".join(ch for ch in str(value).casefold() if ch.isalnum())


def records_from(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("list", "records", "items", "data"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        # Some endpoints return the resource directly.
        if "id" in response:
            return [response]
    return []


def find_by_name(records: list[dict[str, Any]], name: str, resource: str) -> dict[str, Any]:
    wanted = normalize_name(name)
    matches = [item for item in records if normalize_name(item.get("name", "")) == wanted]
    if not matches and wanted == "username":
        matches = [item for item in records if normalize_name(item.get("name", "")) == "username"]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        ids = ", ".join(str(item.get("id")) for item in matches)
        raise CliError(f"Multiple {resource} records matched {name!r}: {ids}")

    available = ", ".join(
        f"{item.get('name')} ({item.get('id')})" for item in records[:20] if isinstance(item, dict)
    )
    suffix = f" Available: {available}" if available else ""
    raise CliError(f"Could not find {resource} named {name!r}.{suffix}")


def find_id(records: list[dict[str, Any]], item_id: str, resource: str) -> dict[str, Any]:
    for item in records:
        if str(item.get("id")) == str(item_id):
            return item
    raise CliError(f"Could not find {resource} with id {item_id!r}")


class ZscalerClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        customer_id: str,
        zidentity_base_url: str | None = None,
        oneapi_base_url: str = DEFAULT_ONEAPI_BASE_URL,
        legacy_zpa_base_url: str = DEFAULT_LEGACY_ZPA_BASE_URL,
        auth_mode: str = "legacy",
        audience: str = DEFAULT_AUDIENCE,
        microtenant_id: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.customer_id = customer_id
        self.auth_mode = normalize_auth_mode(auth_mode)
        self.zidentity_base_url = strip_slash(zidentity_base_url) if zidentity_base_url else None
        self.oneapi_base_url = strip_slash(oneapi_base_url)
        self.legacy_zpa_base_url = strip_slash(legacy_zpa_base_url)
        self.audience = audience
        self.microtenant_id = microtenant_id
        self._access_token: str | None = None

    @property
    def zpa_base_url(self) -> str:
        if self.auth_mode == "legacy":
            return self.legacy_zpa_base_url
        return f"{self.oneapi_base_url}/zpa"

    def token(self) -> str:
        if self._access_token:
            return self._access_token

        if self.auth_mode == "legacy":
            return self.legacy_token()
        return self.oneapi_token()

    def legacy_token(self) -> str:
        url = f"{self.legacy_zpa_base_url}/signin"
        payload = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = load_json(response.read())
        except urllib.error.HTTPError as error:
            raise ApiError("POST", url, error.code, error.read().decode("utf-8", "replace")) from error
        except urllib.error.URLError as error:
            raise CliError(f"Could not reach legacy ZPA sign-in endpoint {url}: {error}") from error

        if not isinstance(body, dict):
            raise CliError(f"Unexpected legacy sign-in response from {url}: {body!r}")
        token = body.get("access_token") or body.get("accessToken")
        if not token:
            raise CliError(f"Legacy sign-in response did not contain an access token: {body}")
        self._access_token = str(token)
        return self._access_token

    def oneapi_token(self) -> str:
        if not self.zidentity_base_url:
            raise CliError("Missing ZIdentity base URL for OneAPI auth. Set ZSCALER_ZIDENTITY_BASE_URL.")
        url = f"{self.zidentity_base_url}/oauth2/v1/token"
        payload = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": self.audience,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = load_json(response.read())
        except urllib.error.HTTPError as error:
            raise ApiError("POST", url, error.code, error.read().decode("utf-8", "replace")) from error
        except urllib.error.URLError as error:
            raise CliError(f"Could not reach ZIdentity token endpoint {url}: {error}") from error

        if not isinstance(body, dict):
            raise CliError(f"Unexpected token response from {url}: {body!r}")
        token = body.get("access_token") or body.get("accessToken")
        if not token:
            raise CliError(f"Token response did not contain an access token: {body}")
        self._access_token = str(token)
        return self._access_token

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        query = dict(query or {})
        if self.microtenant_id is not None:
            query.setdefault("microtenantId", self.microtenant_id)
        url = f"{self.zpa_base_url}{add_query(path, query)}"
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return load_json(response.read())
        except urllib.error.HTTPError as error:
            raise ApiError(method, url, error.code, error.read().decode("utf-8", "replace")) from error
        except urllib.error.URLError as error:
            raise CliError(f"Could not reach ZPA endpoint {url}: {error}") from error

    def policy_set(self, policy_type: str) -> dict[str, Any]:
        path = f"/mgmtconfig/v1/admin/customers/{self.customer_id}/policySet/policyType/{policy_type}"
        response = self.request("GET", path)
        if isinstance(response, dict):
            return response
        raise CliError(f"Unexpected policy set response: {response!r}")

    def policy_set_id(self, policy_type: str) -> str:
        policy_set = self.policy_set(policy_type)
        policy_set_id = policy_set.get("id") or policy_set.get("policySetId")
        if not policy_set_id:
            raise CliError(f"Could not determine policy set ID from response: {policy_set}")
        return str(policy_set_id)

    def rules(self, policy_type: str, search: str | None, page: int, page_size: int) -> Any:
        path = f"/mgmtconfig/v1/admin/customers/{self.customer_id}/policySet/rules/policyType/{policy_type}"
        return self.request("GET", path, query={"search": search, "page": page, "pagesize": page_size})

    def rule(self, policy_set_id: str, rule_id: str) -> dict[str, Any]:
        path = f"/mgmtconfig/v1/admin/customers/{self.customer_id}/policySet/{policy_set_id}/rule/{rule_id}"
        response = self.request("GET", path)
        if isinstance(response, dict):
            return response
        raise CliError(f"Unexpected rule response: {response!r}")

    def update_rule(self, policy_set_id: str, rule_id: str, payload: dict[str, Any], api_version: str) -> Any:
        version = "v2" if api_version == "v2" else "v1"
        path = f"/mgmtconfig/{version}/admin/customers/{self.customer_id}/policySet/{policy_set_id}/rule/{rule_id}"
        return self.request("PUT", path, body=payload)

    def idps(self, search: str | None = None, scim_enabled: bool | None = None) -> list[dict[str, Any]]:
        path = f"/mgmtconfig/v2/admin/customers/{self.customer_id}/idp"
        response = self.request(
            "GET",
            path,
            query={
                "search": search,
                "scimEnabled": str(scim_enabled).lower() if scim_enabled is not None else None,
                "page": 1,
                "pagesize": 500,
            },
        )
        return [item for item in records_from(response) if isinstance(item, dict)]

    def scim_attributes(self, idp_id: str) -> list[dict[str, Any]]:
        path = f"/mgmtconfig/v1/admin/customers/{self.customer_id}/idp/{idp_id}/scimattribute"
        response = self.request("GET", path, query={"page": 1, "pagesize": 500})
        return [item for item in records_from(response) if isinstance(item, dict)]

    def scim_values(self, idp_id: str, attribute_id: str, page: int, page_size: int) -> Any:
        path = (
            f"/userconfig/v1/customers/{self.customer_id}/scimattribute/"
            f"idpId/{idp_id}/attributeId/{attribute_id}"
        )
        return self.request("GET", path, query={"page": page, "pagesize": page_size})


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("No records.")
        return
    widths = []
    for key, label in columns:
        max_value = max(len(str(row.get(key, ""))) for row in rows)
        widths.append(max(len(label), max_value))
    header = "  ".join(label.ljust(width) for (_, label), width in zip(columns, widths))
    print(header)
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(row.get(key, "")).ljust(width) for (key, _), width in zip(columns, widths)))


def resolve_policy_set_id(client: ZscalerClient, args: argparse.Namespace) -> str:
    if getattr(args, "policy_set_id", None):
        return str(args.policy_set_id)
    return client.policy_set_id(args.policy_type)


def resolve_idp(client: ZscalerClient, args: argparse.Namespace) -> dict[str, Any]:
    idps = client.idps(search=getattr(args, "idp_name", None), scim_enabled=True)
    if getattr(args, "idp_id", None):
        return find_id(idps, str(args.idp_id), "IdP")
    return find_by_name(idps, args.idp_name, "IdP")


def resolve_scim_attribute(client: ZscalerClient, idp_id: str, args: argparse.Namespace) -> dict[str, Any]:
    attributes = client.scim_attributes(idp_id)
    if getattr(args, "attribute_id", None):
        return find_id(attributes, str(args.attribute_id), "SCIM attribute")
    return find_by_name(attributes, args.attribute_name, "SCIM attribute")


def operand_entry_values(operand: dict[str, Any]) -> list[dict[str, Any]]:
    values = operand.get("entryValues")
    if isinstance(values, list):
        return [item for item in values if isinstance(item, dict)]
    lhs = operand.get("lhs")
    rhs = operand.get("rhs")
    if lhs is not None and rhs is not None:
        return [{"lhs": str(lhs), "rhs": str(rhs)}]
    return []


def has_scim_value(rule: dict[str, Any], idp_id: str, attribute_id: str, value: str) -> bool:
    for condition in rule.get("conditions", []) or []:
        if not isinstance(condition, dict):
            continue
        for operand in condition.get("operands", []) or []:
            if not isinstance(operand, dict):
                continue
            if operand.get("objectType") != "SCIM":
                continue
            if str(operand.get("idpId", idp_id)) not in (str(idp_id), "None"):
                continue
            for entry in operand_entry_values(operand):
                if str(entry.get("lhs")) == str(attribute_id) and str(entry.get("rhs")) == str(value):
                    return True
    return False


def make_scim_operand(idp: dict[str, Any], attribute: dict[str, Any], value: str) -> dict[str, Any]:
    operand = {
        "objectType": "SCIM",
        "entryValues": [
            {
                "lhs": str(attribute["id"]),
                "rhs": value,
            }
        ],
    }
    if idp.get("id") is not None:
        operand["idpId"] = str(idp["id"])
    if idp.get("name"):
        operand["idpName"] = str(idp["name"])
    return operand


def merge_into_existing_scim_condition(
    rule: dict[str, Any],
    idp: dict[str, Any],
    attribute: dict[str, Any],
    value: str,
) -> bool:
    idp_id = str(idp["id"])
    attribute_id = str(attribute["id"])
    for condition in rule.get("conditions", []) or []:
        if not isinstance(condition, dict):
            continue
        for operand in condition.get("operands", []) or []:
            if not isinstance(operand, dict):
                continue
            if operand.get("objectType") != "SCIM":
                continue
            if str(operand.get("idpId", idp_id)) not in (idp_id, "None"):
                continue

            entries = operand_entry_values(operand)
            if not any(str(entry.get("lhs")) == attribute_id for entry in entries):
                continue

            if "entryValues" in operand and isinstance(operand["entryValues"], list):
                operand["entryValues"].append({"lhs": attribute_id, "rhs": value})
                return True

            condition.setdefault("operator", "OR")
            condition.setdefault("operands", []).append(make_scim_operand(idp, attribute, value))
            return True
    return False


def add_scim_condition(
    rule: dict[str, Any],
    idp: dict[str, Any],
    attribute: dict[str, Any],
    value: str,
    placement: str,
    condition_operator: str,
) -> tuple[dict[str, Any], str]:
    updated = copy.deepcopy(rule)
    idp_id = str(idp["id"])
    attribute_id = str(attribute["id"])
    if has_scim_value(updated, idp_id, attribute_id, value):
        return updated, "unchanged"

    if placement == "merge-same-attribute" and merge_into_existing_scim_condition(updated, idp, attribute, value):
        return updated, "merged"

    updated.setdefault("operator", "AND")
    updated.setdefault("conditions", [])
    updated["conditions"].append(
        {
            "operator": condition_operator,
            "operands": [make_scim_operand(idp, attribute, value)],
        }
    )
    return updated, "added-condition"


def diff_json(before: Any, after: Any, before_name: str = "before", after_name: str = "after") -> str:
    before_lines = dump_json(before).splitlines(keepends=True)
    after_lines = dump_json(after).splitlines(keepends=True)
    return "".join(difflib.unified_diff(before_lines, after_lines, fromfile=before_name, tofile=after_name))


def write_backup(backup_dir: Path, rule_id: str, original: dict[str, Any], modified: dict[str, Any]) -> tuple[Path, Path]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    original_path = backup_dir / f"{timestamp}-rule-{rule_id}-original.json"
    modified_path = backup_dir / f"{timestamp}-rule-{rule_id}-modified.json"
    original_path.write_text(dump_json(original) + "\n", encoding="utf-8")
    modified_path.write_text(dump_json(modified) + "\n", encoding="utf-8")
    return original_path, modified_path


def command_list_rules(client: ZscalerClient, args: argparse.Namespace) -> None:
    response = client.rules(args.policy_type, args.search, args.page, args.page_size)
    rows = [item for item in records_from(response) if isinstance(item, dict)]
    if args.json:
        print_json(response)
    else:
        table(rows, [("id", "ID"), ("name", "Name"), ("action", "Action"), ("ruleOrder", "Order"), ("disabled", "Disabled")])


def command_get_rule(client: ZscalerClient, args: argparse.Namespace) -> None:
    policy_set_id = resolve_policy_set_id(client, args)
    print_json(client.rule(policy_set_id, args.rule_id))


def command_list_idps(client: ZscalerClient, args: argparse.Namespace) -> None:
    rows = client.idps(search=args.search, scim_enabled=args.scim_enabled)
    if args.json:
        print_json(rows)
    else:
        table(rows, [("id", "ID"), ("name", "Name"), ("scimEnabled", "SCIM"), ("enableScimBasedPolicy", "SCIM Policy")])


def command_list_scim_attributes(client: ZscalerClient, args: argparse.Namespace) -> None:
    idp = resolve_idp(client, args)
    rows = client.scim_attributes(str(idp["id"]))
    if args.json:
        print_json(rows)
    else:
        table(rows, [("id", "ID"), ("name", "Name"), ("dataType", "Type"), ("schemaURI", "Schema")])


def command_list_scim_values(client: ZscalerClient, args: argparse.Namespace) -> None:
    idp = resolve_idp(client, args)
    attribute = resolve_scim_attribute(client, str(idp["id"]), args)
    response = client.scim_values(str(idp["id"]), str(attribute["id"]), args.page, args.page_size)
    print_json(response)


def command_add_scim_criteria(client: ZscalerClient, args: argparse.Namespace) -> None:
    policy_set_id = resolve_policy_set_id(client, args)
    idp = resolve_idp(client, args)
    attribute = resolve_scim_attribute(client, str(idp["id"]), args)
    original = client.rule(policy_set_id, args.rule_id)
    modified, status = add_scim_condition(
        original,
        idp,
        attribute,
        args.value,
        args.placement,
        args.condition_operator,
    )

    if status == "unchanged":
        print("No change: this SCIM criterion is already present in the rule.")
        return

    patch = diff_json(original, modified, "current-rule", "modified-rule")
    print(patch if patch else "No JSON diff produced.")
    print(f"Change mode: {status}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to update the ZPA rule.")
        return

    original_path, modified_path = write_backup(Path(args.backup_dir), args.rule_id, original, modified)
    print(f"Backup written: {original_path}")
    print(f"Modified payload written: {modified_path}")
    response = client.update_rule(policy_set_id, args.rule_id, modified, args.update_api_version)
    if response:
        print_json(response)
    else:
        print("Rule update request completed.")


def build_client(args: argparse.Namespace) -> ZscalerClient:
    auth_mode = args.auth_mode or env("ZSCALER_AUTH_MODE", "legacy")
    return ZscalerClient(
        client_id=require_env("ZSCALER_CLIENT_ID"),
        client_secret=require_env("ZSCALER_CLIENT_SECRET"),
        customer_id=args.customer_id or require_env("ZSCALER_CUSTOMER_ID"),
        auth_mode=auth_mode,
        zidentity_base_url=args.zidentity_base_url or env("ZSCALER_ZIDENTITY_BASE_URL"),
        oneapi_base_url=args.oneapi_base_url or env("ZSCALER_ONEAPI_BASE_URL", DEFAULT_ONEAPI_BASE_URL),
        legacy_zpa_base_url=args.zpa_base_url or env("ZSCALER_ZPA_BASE_URL", DEFAULT_LEGACY_ZPA_BASE_URL),
        audience=args.audience,
        microtenant_id=args.microtenant_id if args.microtenant_id is not None else env("ZSCALER_MICROTENANT_ID"),
    )


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--customer-id", help="Override ZSCALER_CUSTOMER_ID.")
    parser.add_argument("--auth-mode", choices=AUTH_MODES, help="Authentication mode. Default: legacy.")
    parser.add_argument("--zpa-base-url", help=f"Override ZSCALER_ZPA_BASE_URL for legacy auth. Default: {DEFAULT_LEGACY_ZPA_BASE_URL}")
    parser.add_argument("--zidentity-base-url", help="Override ZSCALER_ZIDENTITY_BASE_URL for OneAPI auth.")
    parser.add_argument("--oneapi-base-url", help=f"Override ZSCALER_ONEAPI_BASE_URL for OneAPI auth. Default: {DEFAULT_ONEAPI_BASE_URL}")
    parser.add_argument("--audience", default=DEFAULT_AUDIENCE, help=f"OAuth audience. Default: {DEFAULT_AUDIENCE}")
    parser.add_argument("--microtenant-id", help="Optional ZPA microtenant ID. Use 0 for the default microtenant when required.")


def add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--policy-type", default=DEFAULT_POLICY_TYPE, help=f"Policy type. Default: {DEFAULT_POLICY_TYPE}")
    parser.add_argument("--policy-set-id", help="Policy set ID. If omitted, it is resolved from --policy-type.")


def add_idp_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--idp-id", help="IdP ID. If omitted, --idp-name is used.")
    parser.add_argument("--idp-name", default="AzureAD", help="IdP name. Default: AzureAD")


def add_scim_attribute_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attribute-id", help="SCIM attribute ID. If omitted, --attribute-name is used.")
    parser.add_argument("--attribute-name", default="Username", help="SCIM attribute name. Default: Username")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and modify ZPA policy rules.")
    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_rules = subparsers.add_parser("list-rules", help="List policy rules.")
    add_policy_arguments(list_rules)
    list_rules.add_argument("--search", help="Search rules by text.")
    list_rules.add_argument("--page", type=int, default=1)
    list_rules.add_argument("--page-size", type=int, default=500)
    list_rules.add_argument("--json", action="store_true")
    list_rules.set_defaults(func=command_list_rules)

    get_rule = subparsers.add_parser("get-rule", help="Fetch one policy rule as JSON.")
    add_policy_arguments(get_rule)
    get_rule.add_argument("--rule-id", required=True)
    get_rule.set_defaults(func=command_get_rule)

    list_idps = subparsers.add_parser("list-idps", help="List IdP configurations.")
    list_idps.add_argument("--search")
    list_idps.add_argument(
        "--scim-enabled",
        action="store_true",
        default=None,
        help="Only list SCIM-enabled IdPs.",
    )
    list_idps.add_argument("--json", action="store_true")
    list_idps.set_defaults(func=command_list_idps)

    list_attrs = subparsers.add_parser("list-scim-attributes", help="List SCIM attributes for an IdP.")
    add_idp_arguments(list_attrs)
    list_attrs.add_argument("--json", action="store_true")
    list_attrs.set_defaults(func=command_list_scim_attributes)

    list_values = subparsers.add_parser("list-scim-values", help="List values for a SCIM attribute.")
    add_idp_arguments(list_values)
    add_scim_attribute_arguments(list_values)
    list_values.add_argument("--page", type=int, default=1)
    list_values.add_argument("--page-size", type=int, default=500)
    list_values.set_defaults(func=command_list_scim_values)

    add_scim = subparsers.add_parser("add-scim-criteria", help="Add a SCIM attribute criterion to a policy rule.")
    add_policy_arguments(add_scim)
    add_idp_arguments(add_scim)
    add_scim_attribute_arguments(add_scim)
    add_scim.add_argument("--rule-id", required=True)
    add_scim.add_argument("--value", required=True, help="SCIM attribute value to match, e.g. user@example.com.")
    add_scim.add_argument(
        "--placement",
        choices=("merge-same-attribute", "new-condition"),
        default="merge-same-attribute",
        help="Merge into an existing same-attribute SCIM condition when possible, or always add a new condition.",
    )
    add_scim.add_argument(
        "--condition-operator",
        choices=("AND", "OR"),
        default="OR",
        help="Operator for the new condition when one is created. Default: OR.",
    )
    add_scim.add_argument("--update-api-version", choices=("v1", "v2"), default="v2")
    add_scim.add_argument("--backup-dir", default="backups")
    add_scim.add_argument("--apply", action="store_true", help="Apply the update. Without this, only a diff is printed.")
    add_scim.set_defaults(func=command_add_scim_criteria)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        client = build_client(args)
        args.func(client, args)
        return 0
    except CliError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
