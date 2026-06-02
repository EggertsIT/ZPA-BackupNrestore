#!/usr/bin/env python3
"""Backup, diff, and guarded migration workflow for ZPA tenants."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

from zpa_integrity import (
    attach_manifest,
    diff_has_changes,
    preflight_restore,
    validate_backup,
    validate_diff,
)
from zpa_policy_tool import (
    CliError,
    DEFAULT_LEGACY_ZPA_BASE_URL,
    DEFAULT_ONEAPI_BASE_URL,
    ZscalerClient,
    dump_json,
    env,
    normalize_name,
    normalize_auth_mode,
    records_from,
    require_env,
)
from zpa_report import render_report, write_report
from zpa_resources import MIGRATION_ORDER, POLICY_TYPES, RESOURCES, SYSTEM_FIELDS, WRITE_SKIP_FIELDS


BACKUPS_DIR = Path("backups")
APP_DISPLAY_NAME = "ZPA-Backup and Restore"
DEFAULT_PAGE_SIZE = 500


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def profile_client(profile: str, args: argparse.Namespace) -> ZscalerClient:
    prefix = f"ZPA_{profile.upper()}_"
    auth_mode = normalize_auth_mode(env(f"{prefix}AUTH_MODE", args.auth_mode))
    oneapi = env(f"{prefix}ONEAPI_BASE_URL", args.oneapi_base_url)
    zidentity = env(f"{prefix}ZIDENTITY_BASE_URL", args.zidentity_base_url)
    legacy_zpa = env(f"{prefix}ZPA_BASE_URL", args.zpa_base_url)
    return ZscalerClient(
        client_id=require_env(f"{prefix}CLIENT_ID"),
        client_secret=require_env(f"{prefix}CLIENT_SECRET"),
        customer_id=require_env(f"{prefix}CUSTOMER_ID"),
        auth_mode=auth_mode,
        zidentity_base_url=zidentity,
        oneapi_base_url=oneapi,
        legacy_zpa_base_url=legacy_zpa,
        audience=args.audience,
        microtenant_id=env(f"{prefix}MICROTENANT_ID", args.microtenant_id),
    )


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(payload) + "\n", encoding="utf-8")


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CliError(f"File not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CliError(f"Invalid JSON in {path}: {error}") from error


def path_for(client: ZscalerClient, template: str, **values: Any) -> str:
    data = {"customer_id": client.customer_id, **values}
    return template.format(**data)


def list_all(client: ZscalerClient, path: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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


def detail_items(client: ZscalerClient, key: str, meta: dict) -> list[dict[str, Any]]:
    items = list_all(client, path_for(client, meta["path"]))
    detail_path = meta.get("detail_path")
    if not detail_path:
        return items
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
            print(f"warning: failed to fetch {key} detail {item_id}: {error}", file=sys.stderr)
            detailed.append(item)
    return detailed


def get_policy_sets(client: ZscalerClient, policy_types: list[str]) -> dict[str, dict[str, Any]]:
    policy_sets: dict[str, dict[str, Any]] = {}
    for policy_type in policy_types:
        try:
            policy_sets[policy_type] = client.policy_set(policy_type)
        except CliError as error:
            print(f"warning: failed to fetch policy set {policy_type}: {error}", file=sys.stderr)
    return policy_sets


def get_policy_rules(client: ZscalerClient, policy_types: list[str]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    policy_sets = get_policy_sets(client, policy_types)
    for policy_type in policy_types:
        path = f"/mgmtconfig/v1/admin/customers/{client.customer_id}/policySet/rules/policyType/{policy_type}"
        try:
            response = list_all(client, path)
        except CliError as error:
            print(f"warning: failed to fetch policy rules {policy_type}: {error}", file=sys.stderr)
            continue
        policy_set = policy_sets.get(policy_type, {})
        policy_set_id = policy_set.get("id") or policy_set.get("policySetId")
        for rule in response:
            if not isinstance(rule, dict):
                continue
            rule = copy.deepcopy(rule)
            rule["_policyTypeName"] = policy_type
            if policy_set_id is not None:
                rule["_policySetId"] = str(policy_set_id)
            rules.append(rule)
    return rules


def get_identity_refs(client: ZscalerClient) -> dict[str, Any]:
    refs: dict[str, Any] = {"idps": [], "scim_attributes": [], "scim_groups": []}
    idps = client.idps()
    refs["idps"] = idps
    for idp in idps:
        idp_id = idp.get("id")
        if not idp_id:
            continue
        try:
            for attr in client.scim_attributes(str(idp_id)):
                attr = copy.deepcopy(attr)
                attr["_idpId"] = str(idp_id)
                attr["_idpName"] = idp.get("name")
                refs["scim_attributes"].append(attr)
        except CliError as error:
            print(f"warning: failed to fetch SCIM attributes for IdP {idp.get('name')}: {error}", file=sys.stderr)
        try:
            path = f"/userconfig/v1/customers/{client.customer_id}/scimgroup/idpId/{idp_id}"
            for group in list_all(client, path):
                group = copy.deepcopy(group)
                group["_idpId"] = str(idp_id)
                group["_idpName"] = idp.get("name")
                refs["scim_groups"].append(group)
        except CliError as error:
            print(f"warning: failed to fetch SCIM groups for IdP {idp.get('name')}: {error}", file=sys.stderr)
    return refs


def backup_tenant(client: ZscalerClient, label: str, out_path: Path, policy_types: list[str]) -> dict[str, Any]:
    backup = {
        "meta": {
            "label": label,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "customerId": client.customer_id,
            "policyTypes": policy_types,
        },
        "resources": {},
        "errors": {},
    }
    for key, meta in RESOURCES.items():
        try:
            print(f"backup {label}: {key}")
            backup["resources"][key] = detail_items(client, key, meta)
        except CliError as error:
            backup["resources"][key] = None
            backup["errors"][key] = str(error)
    try:
        print(f"backup {label}: identity references")
        backup["resources"].update(get_identity_refs(client))
    except CliError as error:
        backup["errors"]["identity_refs"] = str(error)
    print(f"backup {label}: policy rules")
    backup["resources"]["policy_sets"] = get_policy_sets(client, policy_types)
    backup["resources"]["policy_rules"] = get_policy_rules(client, policy_types)
    attach_manifest(backup)
    save_json(out_path, backup)
    return backup


def name_of(item: dict[str, Any], name_field: str) -> str:
    return str(item.get(name_field) or item.get("name") or item.get("id") or "")


def identity_key(item: dict[str, Any], name_field: str) -> str:
    policy_type = item.get("_policyTypeName")
    name = name_of(item, name_field)
    if policy_type:
        return f"{policy_type}:{normalize_name(name)}"
    return normalize_name(name)


def strip_compare(obj: Any, skip: set[str] | None = None) -> Any:
    skip = set(skip or set())
    if isinstance(obj, list):
        return [strip_compare(item, skip) for item in obj]
    if isinstance(obj, dict):
        return {
            key: strip_compare(value, skip)
            for key, value in sorted(obj.items())
            if key not in SYSTEM_FIELDS and key not in skip and not key.startswith("_")
        }
    return obj


def diff_list(key: str, src_items: list[dict[str, Any]], tgt_items: list[dict[str, Any]]) -> dict[str, Any]:
    meta = {"name_field": "name", "skip_fields": set()} if key == "policy_rules" else RESOURCES[key]
    name_field = meta["name_field"]
    skip_fields = set(meta.get("skip_fields", set()))
    if key == "policy_rules":
        skip_fields.update({"policySetId"})
    src_by_name = {identity_key(item, name_field): item for item in src_items if isinstance(item, dict)}
    tgt_by_name = {identity_key(item, name_field): item for item in tgt_items if isinstance(item, dict)}
    result = {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}

    for item_name, src in src_by_name.items():
        tgt = tgt_by_name.get(item_name)
        if not tgt:
            result["to_create"].append(src)
            continue
        if strip_compare(src, skip_fields) == strip_compare(tgt, skip_fields):
            result["unchanged"].append(src)
        else:
            result["to_update"].append({"source": src, "target": tgt})
    for item_name, tgt in tgt_by_name.items():
        if item_name not in src_by_name:
            result["to_delete"].append(tgt)
    return result


def compute_diff(src_backup: dict[str, Any], tgt_backup: dict[str, Any]) -> dict[str, Any]:
    diff = {
        "meta": {
            "source": src_backup.get("meta", {}),
            "target": tgt_backup.get("meta", {}),
            "sourceManifest": src_backup.get("manifest", {}),
            "targetManifest": tgt_backup.get("manifest", {}),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "resources": {},
        "summary": {},
    }
    for key in MIGRATION_ORDER:
        src_items = src_backup.get("resources", {}).get(key) or []
        tgt_items = tgt_backup.get("resources", {}).get(key) or []
        if src_items is None or tgt_items is None:
            diff["resources"][key] = {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}
        else:
            diff["resources"][key] = diff_list(key, src_items, tgt_items)
        section = diff["resources"][key]
        diff["summary"][key] = {
            "create": len(section["to_create"]),
            "update": len(section["to_update"]),
            "delete": len(section["to_delete"]),
            "unchanged": len(section["unchanged"]),
        }
    return diff


class IDMapper:
    def __init__(self) -> None:
        self.map: dict[str, str] = {}

    def add(self, source_id: Any, target_id: Any) -> None:
        if source_id is None or target_id is None:
            return
        self.map[str(source_id)] = str(target_id)

    def lookup(self, value: Any) -> Any:
        if isinstance(value, (str, int)):
            return self.map.get(str(value), value)
        return value

    def remap(self, obj: Any, *, root: bool = True) -> Any:
        if isinstance(obj, list):
            return [self.remap(item, root=False) for item in obj]
        if not isinstance(obj, dict):
            return self.lookup(obj)
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "id" and root:
                out[key] = value
            elif key in {"id", "idpId", "policySetId", "_policySetId", "lhs", "rhs"}:
                out[key] = self.lookup(value)
            else:
                out[key] = self.remap(value, root=False)
        return out


def ref_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("displayName") or item.get("id") or "")


def seed_by_name(mapper: IDMapper, src_items: list[dict[str, Any]], tgt_items: list[dict[str, Any]], name_field: str) -> None:
    tgt_by_name = {identity_key(item, name_field): item for item in tgt_items if isinstance(item, dict)}
    for src in src_items:
        tgt = tgt_by_name.get(identity_key(src, name_field))
        if tgt:
            mapper.add(src.get("id"), tgt.get("id"))


def seed_identity_refs(mapper: IDMapper, src_backup: dict[str, Any], tgt_backup: dict[str, Any]) -> None:
    src_res = src_backup.get("resources", {})
    tgt_res = tgt_backup.get("resources", {})
    seed_by_name(mapper, src_res.get("idps", []) or [], tgt_res.get("idps", []) or [], "name")

    def scoped_key(item: dict[str, Any]) -> str:
        return f"{normalize_name(item.get('_idpName'))}:{normalize_name(ref_name(item))}"

    for key in ("scim_attributes", "scim_groups"):
        tgt_by_scope = {scoped_key(item): item for item in tgt_res.get(key, []) or [] if isinstance(item, dict)}
        for src in src_res.get(key, []) or []:
            if not isinstance(src, dict):
                continue
            tgt = tgt_by_scope.get(scoped_key(src))
            if tgt:
                mapper.add(src.get("id"), tgt.get("id"))

    for key, meta in RESOURCES.items():
        if meta.get("writable"):
            continue
        seed_by_name(mapper, src_res.get(key, []) or [], tgt_res.get(key, []) or [], meta["name_field"])


def clean_payload(obj: dict[str, Any], meta: dict | None, *, create: bool, target_id: Any | None = None) -> dict[str, Any]:
    skip = set(WRITE_SKIP_FIELDS)
    if meta:
        skip.update(meta.get("skip_fields", set()))
    payload = {
        key: copy.deepcopy(value)
        for key, value in obj.items()
        if key not in SYSTEM_FIELDS and key not in skip and not key.startswith("_")
    }
    if create:
        payload.pop("id", None)
    elif target_id is not None:
        payload["id"] = str(target_id)
    return payload


def print_summary(diff: dict[str, Any]) -> None:
    print("Resource                 Create  Update  Delete  Unchanged")
    print("-----------------------  ------  ------  ------  ---------")
    for key in MIGRATION_ORDER:
        row = diff["summary"][key]
        print(
            f"{key[:23].ljust(23)}  "
            f"{str(row['create']).rjust(6)}  "
            f"{str(row['update']).rjust(6)}  "
            f"{str(row['delete']).rjust(6)}  "
            f"{str(row['unchanged']).rjust(9)}"
        )


def create_resource(client: ZscalerClient, key: str, payload: dict[str, Any]) -> Any:
    meta = RESOURCES[key]
    return client.request("POST", path_for(client, meta["path"]), body=payload)


def update_resource(client: ZscalerClient, key: str, target_id: Any, payload: dict[str, Any]) -> Any:
    meta = RESOURCES[key]
    detail_path = meta.get("detail_path")
    if not detail_path:
        raise CliError(f"Resource {key} does not define an update path")
    return client.request("PUT", path_for(client, detail_path, id=target_id), body=payload)


def delete_resource(client: ZscalerClient, key: str, target_id: Any) -> Any:
    meta = RESOURCES[key]
    detail_path = meta.get("detail_path")
    if not detail_path:
        raise CliError(f"Resource {key} does not define a delete path")
    return client.request("DELETE", path_for(client, detail_path, id=target_id))


def policy_set_id_for_rule(backup: dict[str, Any], rule: dict[str, Any]) -> str | None:
    policy_type = rule.get("_policyTypeName") or rule.get("policyType")
    policy_sets = backup.get("resources", {}).get("policy_sets", {})
    if isinstance(policy_sets, dict) and policy_type in policy_sets:
        policy_set = policy_sets[policy_type]
        return str(policy_set.get("id") or policy_set.get("policySetId") or "")
    return str(rule.get("_policySetId") or rule.get("policySetId") or "") or None


def create_policy_rule(client: ZscalerClient, target_backup: dict[str, Any], rule: dict[str, Any]) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {rule.get('name')}")
    path = f"/mgmtconfig/v2/admin/customers/{client.customer_id}/policySet/{policy_set_id}/rule"
    payload = clean_payload(rule, None, create=True)
    payload["policySetId"] = policy_set_id
    return client.request("POST", path, body=payload)


def update_policy_rule(client: ZscalerClient, target_backup: dict[str, Any], target_rule: dict[str, Any], payload: dict[str, Any]) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, target_rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {target_rule.get('name')}")
    rule_id = target_rule.get("id")
    path = f"/mgmtconfig/v2/admin/customers/{client.customer_id}/policySet/{policy_set_id}/rule/{rule_id}"
    payload["policySetId"] = policy_set_id
    payload["id"] = str(rule_id)
    return client.request("PUT", path, body=payload)


def delete_policy_rule(client: ZscalerClient, target_backup: dict[str, Any], target_rule: dict[str, Any]) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, target_rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {target_rule.get('name')}")
    rule_id = target_rule.get("id")
    path = f"/mgmtconfig/v1/admin/customers/{client.customer_id}/policySet/{policy_set_id}/rule/{rule_id}"
    return client.request("DELETE", path)


def apply_diff(
    client: ZscalerClient,
    diff: dict[str, Any],
    src_backup: dict[str, Any],
    tgt_backup: dict[str, Any],
    *,
    dry_run: bool,
    allow_delete: bool,
    allow_high_impact: bool,
) -> dict[str, Any]:
    mapper = IDMapper()
    seed_identity_refs(mapper, src_backup, tgt_backup)
    result = {"ok": 0, "dry": 0, "errors": 0, "skipped": 0, "log": []}

    def record(action: str, key: str, name: str, status: str, detail: str = "") -> None:
        result["log"].append({"action": action, "resource": key, "name": name, "status": status, "detail": detail})
        if status == "ok":
            result["ok"] += 1
        elif status == "dry":
            result["dry"] += 1
        elif status == "error":
            result["errors"] += 1
        else:
            result["skipped"] += 1
        print(f"{action:<7} {key:<22} {status:<5} {name} {detail}".rstrip())

    for key in MIGRATION_ORDER:
        section = diff["resources"][key]
        if key != "policy_rules":
            meta = RESOURCES[key]
            seed_by_name(mapper, src_backup["resources"].get(key) or [], tgt_backup["resources"].get(key) or [], meta["name_field"])
            if meta.get("high_impact") and not dry_run and not allow_high_impact:
                for obj in section.get("to_create", []):
                    record("CREATE", key, name_of(obj, meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact")
                for change in section.get("to_update", []):
                    record("UPDATE", key, name_of(change.get("source", {}), meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact")
                continue

        for obj in section.get("to_create", []):
            name = name_of(obj, "name")
            try:
                if key == "policy_rules":
                    payload = mapper.remap(obj)
                    if dry_run:
                        record("CREATE", key, name, "dry")
                    else:
                        created = create_policy_rule(client, tgt_backup, payload)
                        if isinstance(created, dict):
                            mapper.add(obj.get("id"), created.get("id"))
                        record("CREATE", key, name, "ok")
                    continue
                payload = mapper.remap(clean_payload(obj, RESOURCES[key], create=True))
                if dry_run:
                    record("CREATE", key, name, "dry")
                else:
                    created = create_resource(client, key, payload)
                    if isinstance(created, dict):
                        mapper.add(obj.get("id"), created.get("id"))
                    record("CREATE", key, name, "ok")
            except CliError as error:
                record("CREATE", key, name, "error", str(error))

        for change in section.get("to_update", []):
            src = change["source"]
            tgt = change["target"]
            name = name_of(src, "name")
            try:
                if key == "policy_rules":
                    payload = mapper.remap(clean_payload(src, None, create=False, target_id=tgt.get("id")))
                    if dry_run:
                        record("UPDATE", key, name, "dry")
                    else:
                        update_policy_rule(client, tgt_backup, tgt, payload)
                        mapper.add(src.get("id"), tgt.get("id"))
                        record("UPDATE", key, name, "ok")
                    continue
                payload = mapper.remap(clean_payload(src, RESOURCES[key], create=False, target_id=tgt.get("id")))
                if dry_run:
                    record("UPDATE", key, name, "dry")
                else:
                    update_resource(client, key, tgt.get("id"), payload)
                    mapper.add(src.get("id"), tgt.get("id"))
                    record("UPDATE", key, name, "ok")
            except CliError as error:
                record("UPDATE", key, name, "error", str(error))

    for key in reversed(MIGRATION_ORDER):
        section = diff["resources"][key]
        if key != "policy_rules":
            meta = RESOURCES[key]
            if meta.get("high_impact") and not dry_run and not allow_high_impact:
                for obj in section.get("to_delete", []):
                    record("DELETE", key, name_of(obj, meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact")
                continue

        for tgt in section.get("to_delete", []):
            name = name_of(tgt, "name")
            if not allow_delete:
                record("DELETE", key, name, "skip", "delete disabled")
                continue
            try:
                if dry_run:
                    record("DELETE", key, name, "dry")
                elif key == "policy_rules":
                    delete_policy_rule(client, tgt_backup, tgt)
                    record("DELETE", key, name, "ok")
                else:
                    delete_resource(client, key, tgt.get("id"))
                    record("DELETE", key, name, "ok")
            except CliError as error:
                record("DELETE", key, name, "error", str(error))
    return result


def backup_paths() -> tuple[Path, Path, Path]:
    stamp = now_stamp()
    return (
        BACKUPS_DIR / f"{stamp}-source.json",
        BACKUPS_DIR / f"{stamp}-target.json",
        BACKUPS_DIR / f"{stamp}-diff.json",
    )


def policy_types_for_restore_source(source_backup: dict[str, Any], fallback: list[str]) -> list[str]:
    policy_types = source_backup.get("meta", {}).get("policyTypes")
    if isinstance(policy_types, list):
        clean = [str(policy_type) for policy_type in policy_types if policy_type]
        if clean:
            return clean
    return fallback


def effective_policy_types(policy_types: list[str]) -> list[str]:
    return policy_types or list(POLICY_TYPES)


def command_backup(args: argparse.Namespace) -> None:
    source_path, target_path, _ = backup_paths()
    if args.tenant in ("source", "both"):
        backup_tenant(profile_client("source", args), "source", source_path, args.policy_type)
        print(f"source backup: {source_path}")
    if args.tenant in ("target", "both"):
        backup_tenant(profile_client("target", args), "target", target_path, args.policy_type)
        print(f"target backup: {target_path}")


def command_diff(args: argparse.Namespace) -> None:
    source = load_json_file(Path(args.source_backup))
    target = load_json_file(Path(args.target_backup))
    if not args.allow_invalid_backup:
        issues = [
            *(f"source backup: {issue}" for issue in validate_backup(source, strict=args.strict_manifest)),
            *(f"target backup: {issue}" for issue in validate_backup(target, strict=args.strict_manifest)),
        ]
        if issues:
            raise CliError("Backup validation failed:\n" + "\n".join(f"- {issue}" for issue in issues))
    diff = compute_diff(source, target)
    print_summary(diff)
    if args.out:
        save_json(Path(args.out), diff)
        print(f"diff written: {args.out}")
    if args.report_out:
        write_report(
            Path(args.report_out),
            title=f"{APP_DISPLAY_NAME} Diff Report",
            source_backup=source,
            target_backup=target,
            diff=diff,
        )
        print(f"report written: {args.report_out}")


def command_plan(args: argparse.Namespace) -> None:
    source_path, target_path, diff_path = backup_paths()
    report_path = diff_path.with_suffix(".html")
    source = backup_tenant(profile_client("source", args), "source", source_path, args.policy_type)
    target = backup_tenant(profile_client("target", args), "target", target_path, args.policy_type)
    diff = compute_diff(source, target)
    save_json(diff_path, diff)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} Plan Report",
        source_backup=source,
        target_backup=target,
        diff=diff,
    )
    print_summary(diff)
    print(f"source backup: {source_path}")
    print(f"target backup: {target_path}")
    print(f"diff: {diff_path}")
    print(f"report: {report_path}")


def command_restore_plan(args: argparse.Namespace) -> None:
    source_path = Path(args.source_backup)
    source = load_json_file(source_path)
    if not args.allow_invalid_backup:
        issues = validate_backup(source, strict=True)
        if issues:
            raise CliError("Source backup validation failed:\n" + "\n".join(f"- {issue}" for issue in issues))

    stamp = now_stamp()
    target_path = BACKUPS_DIR / f"{stamp}-restore-target.json"
    diff_path = BACKUPS_DIR / f"{stamp}-restore-diff.json"
    report_path = diff_path.with_suffix(".html")
    policy_types = policy_types_for_restore_source(source, args.policy_type)

    target = backup_tenant(profile_client("target", args), "target", target_path, policy_types)
    diff = compute_diff(source, target)
    save_json(diff_path, diff)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} Restore Plan Report",
        source_backup=source,
        target_backup=target,
        diff=diff,
    )
    print_summary(diff)
    print(f"source backup: {source_path}")
    print(f"target backup: {target_path}")
    print(f"diff: {diff_path}")
    print(f"report: {report_path}")


def command_apply(args: argparse.Namespace) -> None:
    if not args.yes and not args.dry_run:
        raise CliError("Refusing to write without --yes. Run plan/diff first and review the output.")
    source = load_json_file(Path(args.source_backup))
    target = load_json_file(Path(args.target_backup))
    diff = load_json_file(Path(args.diff))
    issues = preflight_restore(
        source,
        target,
        diff,
        allow_failed_backups=args.allow_failed_backups,
    )
    if issues and not args.ignore_preflight:
        raise CliError("Preflight failed:\n" + "\n".join(f"- {issue}" for issue in issues))
    if not diff_has_changes(diff):
        print("No changes in diff. Nothing to apply.")
        return
    result = apply_diff(
        profile_client("target", args),
        diff,
        source,
        target,
        dry_run=args.dry_run,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
    )
    action_label = "restore" if getattr(args, "command", "") == "restore" else "apply"
    out_path = BACKUPS_DIR / f"{now_stamp()}-{action_label}-result.json"
    report_path = out_path.with_suffix(".html")
    save_json(out_path, result)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} {action_label.title()} Report",
        source_backup=source,
        target_backup=target,
        diff=diff,
        apply_result=result,
    )
    print(f"{action_label} result: {out_path}")
    print(f"report: {report_path}")


def command_restore(args: argparse.Namespace) -> None:
    command_apply(args)


def command_report(args: argparse.Namespace) -> None:
    source = load_json_file(Path(args.source_backup)) if args.source_backup else None
    target = load_json_file(Path(args.target_backup)) if args.target_backup else None
    diff = load_json_file(Path(args.diff)) if args.diff else None
    apply_result = load_json_file(Path(args.apply_result)) if args.apply_result else None
    write_report(
        Path(args.out),
        title=args.title,
        source_backup=source,
        target_backup=target,
        diff=diff,
        apply_result=apply_result,
        include_coverage=not args.no_coverage,
    )
    print(f"report written: {args.out}")


def command_coverage(args: argparse.Namespace) -> None:
    rows = []
    for key, meta in RESOURCES.items():
        rows.append(
            {
                "resource": key,
                "mode": "write" if meta.get("writable") else "read",
                "endpoint": meta.get("path", ""),
                "depends_on": ", ".join(meta.get("depends_on", [])),
                "notes": meta.get("notes", ""),
            }
        )
    if args.json:
        print(dump_json(rows))
        return
    print("Resource                  Mode   Endpoint")
    print("------------------------  -----  --------")
    for row in rows:
        print(f"{row['resource'][:24].ljust(24)}  {row['mode'][:5].ljust(5)}  {row['endpoint']}")


def command_validate(args: argparse.Namespace) -> None:
    if not args.backup and not args.diff:
        raise CliError("Nothing to validate. Pass --backup and/or --diff.")
    failed = False
    for backup_path in args.backup:
        backup = load_json_file(Path(backup_path))
        issues = validate_backup(backup, strict=args.strict_manifest)
        if issues:
            failed = True
            print(f"{backup_path}: invalid")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"{backup_path}: valid")
    for diff_path in args.diff:
        diff = load_json_file(Path(diff_path))
        issues = validate_diff(diff)
        if issues:
            failed = True
            print(f"{diff_path}: invalid")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"{diff_path}: valid")
    if failed:
        raise CliError("Validation failed")


def command_preflight(args: argparse.Namespace) -> None:
    source = load_json_file(Path(args.source_backup))
    target = load_json_file(Path(args.target_backup))
    diff = load_json_file(Path(args.diff))
    issues = preflight_restore(
        source,
        target,
        diff,
        allow_failed_backups=args.allow_failed_backups,
    )
    if issues:
        print("Preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        raise CliError("Preflight failed")
    if not diff_has_changes(diff):
        print("Preflight passed. Diff contains no changes.")
    else:
        print("Preflight passed. Diff contains changes.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZPA tenant backup/diff/restore tool.")
    parser.add_argument("--auth-mode", choices=("legacy", "oneapi"), default=env("ZSCALER_AUTH_MODE", "legacy"))
    parser.add_argument("--zpa-base-url", default=env("ZSCALER_ZPA_BASE_URL", DEFAULT_LEGACY_ZPA_BASE_URL))
    parser.add_argument("--oneapi-base-url", default=env("ZSCALER_ONEAPI_BASE_URL", DEFAULT_ONEAPI_BASE_URL))
    parser.add_argument("--zidentity-base-url", default=env("ZSCALER_ZIDENTITY_BASE_URL"))
    parser.add_argument("--audience", default="https://api.zscaler.com")
    parser.add_argument("--microtenant-id")
    parser.add_argument(
        "--policy-type",
        action="append",
        default=[],
        help="Policy rule type to include. Can be repeated. Default: all supported policy rule types.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Back up source, target, or both tenants.")
    backup.add_argument("tenant", choices=("source", "target", "both"), nargs="?", default="both")
    backup.set_defaults(func=command_backup)

    diff = sub.add_parser("diff", help="Compare two existing backup files.")
    diff.add_argument("--source-backup", required=True)
    diff.add_argument("--target-backup", required=True)
    diff.add_argument("--out")
    diff.add_argument("--report-out")
    diff.add_argument("--strict-manifest", action="store_true", help="Require backups to include a valid manifest.")
    diff.add_argument("--allow-invalid-backup", action="store_true", help="Skip backup validation before diffing.")
    diff.set_defaults(func=command_diff)

    plan = sub.add_parser("plan", help="Back up both tenants and produce a diff. No changes are applied.")
    plan.set_defaults(func=command_plan)

    restore_plan = sub.add_parser(
        "restore-plan",
        help="Use an existing source backup as the desired state, then back up target and produce a restore diff.",
    )
    restore_plan.add_argument("--source-backup", required=True)
    restore_plan.add_argument("--allow-invalid-backup", action="store_true", help="Skip validation of the source backup.")
    restore_plan.set_defaults(func=command_restore_plan)

    apply = sub.add_parser("apply", help="Automation alias for restoring a reviewed diff to the target tenant.")
    apply.add_argument("--source-backup", required=True)
    apply.add_argument("--target-backup", required=True)
    apply.add_argument("--diff", required=True)
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--dry-run", action="store_true", help="Log write operations without calling write endpoints.")
    apply.add_argument("--allow-delete", action="store_true", help="Allow deletes. By default deletes are skipped.")
    apply.add_argument("--allow-high-impact", action="store_true", help="Allow writes to high-impact resources such as microtenants.")
    apply.add_argument("--allow-failed-backups", action="store_true", help="Allow apply when backup files contain endpoint errors.")
    apply.add_argument("--ignore-preflight", action="store_true", help="Bypass restore preflight validation.")
    apply.set_defaults(func=command_apply)

    restore = sub.add_parser("restore", help="Restore a reviewed source backup into the target tenant.")
    restore.add_argument("--source-backup", required=True)
    restore.add_argument("--target-backup", required=True)
    restore.add_argument("--diff", required=True)
    restore.add_argument("--yes", action="store_true")
    restore.add_argument("--dry-run", action="store_true", help="Log write operations without calling write endpoints.")
    restore.add_argument("--allow-delete", action="store_true", help="Allow deletes. By default deletes are skipped.")
    restore.add_argument("--allow-high-impact", action="store_true", help="Allow writes to high-impact resources such as microtenants.")
    restore.add_argument("--allow-failed-backups", action="store_true", help="Allow restore when backup files contain endpoint errors.")
    restore.add_argument("--ignore-preflight", action="store_true", help="Bypass restore preflight validation.")
    restore.set_defaults(func=command_restore)

    report = sub.add_parser("report", help="Generate an HTML report from backup/diff/restore files.")
    report.add_argument("--source-backup")
    report.add_argument("--target-backup")
    report.add_argument("--diff")
    report.add_argument("--apply-result")
    report.add_argument("--out", required=True)
    report.add_argument("--title", default=f"{APP_DISPLAY_NAME} Report")
    report.add_argument("--no-coverage", action="store_true")
    report.set_defaults(func=command_report)

    coverage = sub.add_parser("coverage", help="Show current ZPA backup/restore resource coverage.")
    coverage.add_argument("--json", action="store_true")
    coverage.set_defaults(func=command_coverage)

    validate = sub.add_parser("validate", help="Validate backup and diff files.")
    validate.add_argument("--backup", action="append", default=[], help="Backup JSON file. Can be repeated.")
    validate.add_argument("--diff", action="append", default=[], help="Diff JSON file. Can be repeated.")
    validate.add_argument("--strict-manifest", action="store_true", help="Require backup manifest and checksum.")
    validate.set_defaults(func=command_validate)

    preflight = sub.add_parser("preflight", help="Validate a restore/apply set before writing.")
    preflight.add_argument("--source-backup", required=True)
    preflight.add_argument("--target-backup", required=True)
    preflight.add_argument("--diff", required=True)
    preflight.add_argument("--allow-failed-backups", action="store_true")
    preflight.set_defaults(func=command_preflight)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.policy_type = effective_policy_types(args.policy_type)
    invalid = sorted(set(args.policy_type) - set(POLICY_TYPES))
    if invalid:
        parser.error(f"unsupported policy type(s): {', '.join(invalid)}")
    try:
        args.func(args)
        return 0
    except CliError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
