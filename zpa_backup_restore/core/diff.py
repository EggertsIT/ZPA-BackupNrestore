"""Pure, tenant-independent backup comparison."""

from __future__ import annotations

import time
from typing import Any

from zpa_backup_restore.core.catalog import MIGRATION_ORDER, RESOURCES, SYSTEM_FIELDS
from zpa_backup_restore.resources.application_segments import special_operation_sections
from zpa_backup_restore.resources.policy_rules import policy_order_section

SPECIAL_DIFF_RESOURCES = (
    "application_segment_moves",
    "application_segment_shares",
    "policy_rule_order",
)


def normalize_name(value: Any) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def name_of(item: dict[str, Any], name_field: str) -> str:
    return str(item.get(name_field) or item.get("name") or item.get("id") or "")


def identity_key(item: dict[str, Any], name_field: str) -> str:
    policy_type = item.get("_policyTypeName")
    name = name_of(item, name_field)
    return f"{policy_type}:{normalize_name(name)}" if policy_type else normalize_name(name)


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
        skip_fields.add("policySetId")
        skip_fields.add("ruleOrder")
    src_by_name = {identity_key(item, name_field): item for item in src_items if isinstance(item, dict)}
    tgt_by_name = {identity_key(item, name_field): item for item in tgt_items if isinstance(item, dict)}
    result = {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}

    for item_name, source in src_by_name.items():
        target = tgt_by_name.get(item_name)
        if not target:
            result["to_create"].append(source)
        elif strip_compare(source, skip_fields) == strip_compare(target, skip_fields):
            result["unchanged"].append(source)
        else:
            result["to_update"].append({"source": source, "target": target})
    for item_name, target in tgt_by_name.items():
        if item_name not in src_by_name:
            result["to_delete"].append(target)
    return result


def compute_diff(src_backup: dict[str, Any], tgt_backup: dict[str, Any]) -> dict[str, Any]:
    """Compute a stable name-based restore diff between two backups."""
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
        diff["resources"][key] = diff_list(key, src_items, tgt_items)
        section = diff["resources"][key]
        diff["summary"][key] = {
            "create": len(section["to_create"]),
            "update": len(section["to_update"]),
            "delete": len(section["to_delete"]),
            "unchanged": len(section["unchanged"]),
        }
    order_section = policy_order_section(
        src_backup.get("resources", {}).get("policy_rules") or [],
        tgt_backup.get("resources", {}).get("policy_rules") or [],
    )
    diff["resources"]["policy_rule_order"] = order_section
    diff["summary"]["policy_rule_order"] = {
        "create": 0,
        "update": len(order_section["to_update"]),
        "delete": 0,
        "unchanged": len(order_section["unchanged"]),
    }
    special_sections = special_operation_sections(
        src_backup.get("resources", {}).get("application_segments") or [],
        tgt_backup.get("resources", {}).get("application_segments") or [],
    )
    for key, section in special_sections.items():
        diff["resources"][key] = section
        diff["summary"][key] = {
            "create": 0,
            "update": len(section["to_update"]),
            "delete": 0,
            "unchanged": 0,
        }
    return diff


def diff_action_totals(diff: dict[str, Any]) -> dict[str, int]:
    totals = {"create": 0, "update": 0, "delete": 0}
    for section in diff.get("resources", {}).values():
        if not isinstance(section, dict):
            continue
        totals["create"] += len(section.get("to_create", []) or [])
        totals["update"] += len(section.get("to_update", []) or [])
        totals["delete"] += len(section.get("to_delete", []) or [])
    return totals


__all__ = [
    "compute_diff",
    "diff_action_totals",
    "diff_list",
    "identity_key",
    "name_of",
    "normalize_name",
    "strip_compare",
    "SPECIAL_DIFF_RESOURCES",
]
