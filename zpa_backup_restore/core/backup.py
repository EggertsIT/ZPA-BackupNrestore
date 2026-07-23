"""Read-only tenant backup service."""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path
from typing import Any, Protocol

from zpa_backup_restore.core.catalog import RESOURCES
from zpa_backup_restore.core.integrity import attach_manifest, count_resource
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources.identity_references import saml_attributes_path, scim_groups_path
from zpa_backup_restore.resources.policy_rules import policy_rules_path
from zpa_backup_restore.storage.backups import (
    DEFAULT_BACKUP_PASSPHRASE_ENV,
    DEFAULT_OPENSSL_BIN,
    OPENSSL_CIPHER,
    backup_passphrase,
    openssl_binary,
    openssl_decrypt_command,
    save_backup_json,
)


DEFAULT_PAGE_SIZE = 500


class BackupClient(Protocol):
    customer_id: str

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any: ...

    def policy_set(self, policy_type: str) -> dict[str, Any]: ...

    def idps(self, search: str | None = None, scim_enabled: bool | None = None) -> list[dict[str, Any]]: ...

    def scim_attributes(self, idp_id: str) -> list[dict[str, Any]]: ...


def records_from(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("list", "records", "items", "data"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        if "id" in response:
            return [response]
    return []


def strip_backup_fields(value: Any, fields: set[str]) -> Any:
    """Remove sensitive fields recursively before a record enters a snapshot."""
    if not fields:
        return value
    if isinstance(value, dict):
        return {
            key: strip_backup_fields(item, fields)
            for key, item in value.items()
            if key not in fields
        }
    if isinstance(value, list):
        return [strip_backup_fields(item, fields) for item in value]
    return value


def path_for(client: BackupClient, template: str, **values: Any) -> str:
    return template.format(customer_id=client.customer_id, **values)


def item_count_text(value: Any) -> str:
    count = count_resource(value)
    if count is None:
        return "unavailable"
    return f"{count} item" if count == 1 else f"{count} items"


def print_run_header(command: str, *, mode: str, policy_types: list[str] | None = None) -> None:
    print(f"run: {command} start")
    print(f"run: mode={mode}")
    print("run: artifact dir=backups")
    if policy_types is not None:
        print(f"run: policy types={', '.join(policy_types)}")


def expected_detail_skip(key: str, item_id: Any, error: CliError) -> bool:
    return key == "microtenants" and str(item_id) == "0" and "resource.not.found" in str(error)


def record_warning(warnings: list[str], message: str, *, detail: str, log_level: str) -> None:
    warnings.append(message)
    if log_level == "verbose":
        print(f"warning: {message}: {detail}", file=sys.stderr)


def print_warning_summary(scope: str, warnings: list[str]) -> None:
    if not warnings:
        print(f"{scope} warnings: 0")
        return
    print(f"{scope} warnings: {len(warnings)}")
    for warning in warnings:
        print(f"{scope} warning: {warning}")


def list_all(
    client: BackupClient,
    path: str,
    query: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read all pages using the common ZPA pagination shapes."""
    query = dict(query or {})
    items: list[dict[str, Any]] = []
    page = int(query.pop("page", 1) or 1)
    page_size = int(query.pop("pagesize", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE)
    while True:
        response = client.request("GET", path, query={**query, "page": page, "pagesize": page_size})
        page_items = [item for item in records_from(response) if isinstance(item, dict)]
        items.extend(page_items)
        total_pages = None
        if isinstance(response, dict):
            total_pages = response.get("totalPages") or response.get("total_pages")
        if total_pages is not None:
            if page >= int(total_pages):
                break
        elif len(page_items) < page_size:
            break
        page += 1
    return items


def list_cursor(
    client: BackupClient,
    path: str,
    query: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read cursor-paginated ZPA endpoints using pageId/nextPage."""
    query = dict(query or {})
    items: list[dict[str, Any]] = []
    page_id = query.pop("pageId", None)
    page_size = int(query.pop("pageSize", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE)
    while True:
        page_query = {**query, "pageSize": page_size}
        if page_id:
            page_query["pageId"] = page_id
        response = client.request("GET", path, query=page_query)
        items.extend(
            item for item in records_from(response) if isinstance(item, dict)
        )
        next_page = response.get("nextPage") if isinstance(response, dict) else None
        if not next_page or str(next_page) == str(page_id):
            break
        page_id = next_page
    return items


def detail_items(
    client: BackupClient,
    key: str,
    meta: dict,
    *,
    warnings: list[str],
    log_level: str,
) -> list[dict[str, Any]]:
    """Fetch resource records according to that resource module's strategy."""
    path = path_for(client, meta["path"])
    pagination = meta.get("pagination", "page")
    if pagination == "none":
        raw_items = records_from(client.request("GET", path))
        if key == "zscaler_clouds":
            items = [
                item
                if isinstance(item, dict)
                else {"id": str(item), "name": str(item)}
                for item in raw_items
            ]
        else:
            items = [item for item in raw_items if isinstance(item, dict)]
    elif pagination == "cursor":
        items = list_cursor(client, path)
    else:
        items = list_all(client, path)
    detail_path = meta.get("detail_path")
    backup_skip_fields = set(meta.get("backup_skip_fields", set()))
    if not detail_path:
        return strip_backup_fields(items, backup_skip_fields)
    if meta.get("detail_strategy", "detail") == "list":
        if log_level == "verbose":
            print(f"detail: using listed {key} records; per-item detail fetch disabled by resource catalog")
        return strip_backup_fields(items, backup_skip_fields)
    detailed = []
    for item in items:
        item_id = item.get(meta["id_field"])
        if not item_id:
            detailed.append(item)
            continue
        try:
            detail = client.request("GET", path_for(client, detail_path, id=item_id))
            detailed.append(detail if isinstance(detail, dict) else item)
        except CliError as error:
            if expected_detail_skip(key, item_id, error):
                print(f"info: using listed {key} record for default item {item_id}; detail endpoint returned not found")
                if log_level == "verbose":
                    print(f"detail: skipped {key} detail {item_id}: {error}", file=sys.stderr)
            else:
                record_warning(
                    warnings,
                    f"failed to fetch {key} detail {item_id}",
                    detail=str(error),
                    log_level=log_level,
                )
            detailed.append(item)
    return strip_backup_fields(detailed, backup_skip_fields)


def get_policy_sets(
    client: BackupClient,
    policy_types: list[str],
    *,
    warnings: list[str] | None = None,
    log_level: str = "normal",
) -> dict[str, dict[str, Any]]:
    policy_sets: dict[str, dict[str, Any]] = {}
    warnings = warnings if warnings is not None else []
    for policy_type in policy_types:
        try:
            policy_sets[policy_type] = client.policy_set(policy_type)
        except CliError as error:
            record_warning(
                warnings,
                f"failed to fetch policy set {policy_type}",
                detail=str(error),
                log_level=log_level,
            )
    return policy_sets


def get_policy_rules(
    client: BackupClient,
    policy_types: list[str],
    *,
    warnings: list[str],
    log_level: str,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    policy_sets = get_policy_sets(client, policy_types, warnings=warnings, log_level=log_level)
    for policy_type in policy_types:
        try:
            response = list_all(client, policy_rules_path(client.customer_id, policy_type))
        except CliError as error:
            record_warning(
                warnings,
                f"failed to fetch policy rules {policy_type}",
                detail=str(error),
                log_level=log_level,
            )
            continue
        policy_set = policy_sets.get(policy_type, {})
        policy_set_id = policy_set.get("id") or policy_set.get("policySetId")
        for rule in response:
            rule = copy.deepcopy(rule)
            rule["_policyTypeName"] = policy_type
            if policy_set_id is not None:
                rule["_policySetId"] = str(policy_set_id)
            rules.append(rule)
    return rules


def get_identity_refs(client: BackupClient, *, warnings: list[str], log_level: str) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "idps": [],
        "saml_attributes": [],
        "scim_attributes": [],
        "scim_groups": [],
    }
    idps = client.idps()
    refs["idps"] = idps
    for idp in idps:
        idp_id = idp.get("id")
        if not idp_id:
            continue
        try:
            for attribute in list_all(
                client,
                saml_attributes_path(client.customer_id, str(idp_id)),
            ):
                attribute = copy.deepcopy(attribute)
                attribute["_idpId"] = str(idp_id)
                attribute["_idpName"] = idp.get("name")
                refs["saml_attributes"].append(attribute)
        except CliError as error:
            record_warning(
                warnings,
                f"failed to fetch SAML attributes for IdP {idp.get('name')}",
                detail=str(error),
                log_level=log_level,
            )
        try:
            for attribute in client.scim_attributes(str(idp_id)):
                attribute = copy.deepcopy(attribute)
                attribute["_idpId"] = str(idp_id)
                attribute["_idpName"] = idp.get("name")
                refs["scim_attributes"].append(attribute)
        except CliError as error:
            record_warning(
                warnings,
                f"failed to fetch SCIM attributes for IdP {idp.get('name')}",
                detail=str(error),
                log_level=log_level,
            )
        try:
            for group in list_all(client, scim_groups_path(client.customer_id, str(idp_id))):
                group = copy.deepcopy(group)
                group["_idpId"] = str(idp_id)
                group["_idpName"] = idp.get("name")
                refs["scim_groups"].append(group)
        except CliError as error:
            record_warning(
                warnings,
                f"failed to fetch SCIM groups for IdP {idp.get('name')}",
                detail=str(error),
                log_level=log_level,
            )
    return refs


def backup_tenant(
    client: BackupClient,
    label: str,
    out_path: Path,
    policy_types: list[str],
    *,
    log_level: str = "normal",
    encrypt_backups: bool = False,
    passphrase_env: str = DEFAULT_BACKUP_PASSPHRASE_ENV,
    openssl_bin: str = DEFAULT_OPENSSL_BIN,
) -> dict[str, Any]:
    """Capture a complete read-only tenant snapshot."""
    if encrypt_backups:
        backup_passphrase(passphrase_env)
        openssl_binary(openssl_bin)

    warnings: list[str] = []
    backup: dict[str, Any] = {
        "meta": {
            "label": label,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "customerId": client.customer_id,
            "policyTypes": policy_types,
        },
        "resources": {},
        "errors": {},
        "warnings": warnings,
    }
    print_run_header("backup", mode=label, policy_types=policy_types)
    for key, meta in RESOURCES.items():
        try:
            print(f"backup {label}: {key} start")
            backup["resources"][key] = detail_items(
                client,
                key,
                meta,
                warnings=warnings,
                log_level=log_level,
            )
            print(f"backup {label}: {key} done ({item_count_text(backup['resources'][key])})")
        except CliError as error:
            backup["resources"][key] = []
            if not meta.get("optional"):
                backup["errors"][key] = str(error)
            record_warning(warnings, f"failed to back up {key}", detail=str(error), log_level=log_level)

    try:
        print(f"backup {label}: identity references start")
        backup["resources"].update(get_identity_refs(client, warnings=warnings, log_level=log_level))
        counts = ", ".join(
            f"{key}={item_count_text(backup['resources'].get(key))}"
            for key in ("idps", "saml_attributes", "scim_attributes", "scim_groups")
        )
        print(f"backup {label}: identity references done ({counts})")
    except CliError as error:
        backup["errors"]["identity_refs"] = str(error)
        record_warning(warnings, "failed to back up identity references", detail=str(error), log_level=log_level)

    print(f"backup {label}: policy rules start")
    backup["resources"]["policy_sets"] = get_policy_sets(
        client, policy_types, warnings=warnings, log_level=log_level
    )
    backup["resources"]["policy_rules"] = get_policy_rules(
        client, policy_types, warnings=warnings, log_level=log_level
    )
    print(
        f"backup {label}: policy rules done "
        f"(policy_sets={item_count_text(backup['resources']['policy_sets'])}, "
        f"rules={item_count_text(backup['resources']['policy_rules'])})"
    )
    print_warning_summary(f"backup {label}", warnings)
    attach_manifest(backup)
    save_backup_json(
        out_path,
        backup,
        encrypted=encrypt_backups,
        passphrase_env=passphrase_env,
        openssl_bin=openssl_bin,
    )
    if encrypt_backups:
        print(f"backup {label}: encrypted with OpenSSL {OPENSSL_CIPHER} PBKDF2")
        print(
            f"backup {label}: set {passphrase_env}, "
            f"then decrypt with: {openssl_decrypt_command(out_path, passphrase_env)}"
        )
    print(f"backup {label}: complete ({item_count_text(backup['resources'])}; warnings={len(warnings)})")
    return backup


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "backup_tenant",
    "detail_items",
    "expected_detail_skip",
    "get_identity_refs",
    "get_policy_rules",
    "get_policy_sets",
    "item_count_text",
    "list_all",
    "list_cursor",
    "path_for",
    "print_run_header",
    "print_warning_summary",
    "record_warning",
    "strip_backup_fields",
]
