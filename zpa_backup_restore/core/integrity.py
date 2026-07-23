"""Backup manifests, validation, and restore preflight checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from zpa_backup_restore.core.selection import (
    compute_restore_diff,
    scope_from_diff,
    validate_restore_scope,
)
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources.registry import (
    MIGRATION_ORDER,
    READ_ONLY_REFERENCE_RESOURCES,
    RESOURCES,
    migration_order_issues,
)


BACKUP_SCHEMA_VERSION = "1.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def backup_for_digest(backup: dict[str, Any]) -> dict[str, Any]:
    copy = json.loads(json.dumps(backup))
    copy.pop("manifest", None)
    return copy


def backup_digest(backup: dict[str, Any]) -> str:
    return sha256_text(canonical_json(backup_for_digest(backup)))


def count_resource(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return len(value)
    return 1 if value else 0


def resource_counts(backup: dict[str, Any]) -> dict[str, int | None]:
    resources = backup.get("resources", {})
    keys = list(RESOURCES) + READ_ONLY_REFERENCE_RESOURCES + ["policy_sets", "policy_rules"]
    return {key: count_resource(resources.get(key)) for key in keys}


def build_manifest(backup: dict[str, Any]) -> dict[str, Any]:
    errors = backup.get("errors", {}) or {}
    return {
        "schemaVersion": BACKUP_SCHEMA_VERSION,
        "customerId": backup.get("meta", {}).get("customerId"),
        "label": backup.get("meta", {}).get("label"),
        "timestamp": backup.get("meta", {}).get("timestamp"),
        "policyTypes": backup.get("meta", {}).get("policyTypes", []),
        "resourceCounts": resource_counts(backup),
        "errorCount": len(errors),
        "errors": sorted(errors),
        "sha256": backup_digest(backup),
    }


def attach_manifest(backup: dict[str, Any]) -> dict[str, Any]:
    backup["manifest"] = build_manifest(backup)
    return backup


def validate_backup(backup: dict[str, Any], *, strict: bool = False) -> list[str]:
    issues: list[str] = []
    if not isinstance(backup, dict):
        return ["backup root must be a JSON object"]
    if not isinstance(backup.get("meta"), dict):
        issues.append("missing meta object")
    if not isinstance(backup.get("resources"), dict):
        issues.append("missing resources object")
        return issues

    meta = backup.get("meta", {})
    if not meta.get("customerId"):
        issues.append("missing meta.customerId")
    if not meta.get("timestamp"):
        issues.append("missing meta.timestamp")

    resources = backup.get("resources", {})
    for key in MIGRATION_ORDER:
        if key not in resources:
            if not RESOURCES.get(key, {}).get("optional"):
                issues.append(f"missing resources.{key}")
        elif resources[key] is not None and not isinstance(resources[key], list):
            issues.append(f"resources.{key} must be a list or null")

    for key in READ_ONLY_REFERENCE_RESOURCES:
        if key in resources and resources[key] is not None and not isinstance(resources[key], list):
            issues.append(f"resources.{key} must be a list or null")

    if "policy_sets" in resources and resources["policy_sets"] is not None and not isinstance(resources["policy_sets"], dict):
        issues.append("resources.policy_sets must be an object or null")
    if "policy_rules" in resources and resources["policy_rules"] is not None and not isinstance(resources["policy_rules"], list):
        issues.append("resources.policy_rules must be a list or null")

    manifest = backup.get("manifest")
    if not isinstance(manifest, dict):
        if strict:
            issues.append("missing manifest")
        return issues

    if manifest.get("sha256") != backup_digest(backup):
        issues.append("manifest sha256 does not match backup contents")
    if manifest.get("schemaVersion") != BACKUP_SCHEMA_VERSION:
        issues.append(f"unsupported manifest schemaVersion {manifest.get('schemaVersion')!r}")
    return issues


def validate_diff(diff: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(diff, dict):
        return ["diff root must be a JSON object"]
    if not isinstance(diff.get("resources"), dict):
        issues.append("missing diff resources object")
        return issues
    for key in MIGRATION_ORDER:
        section = diff["resources"].get(key)
        if not isinstance(section, dict):
            if not RESOURCES.get(key, {}).get("optional"):
                issues.append(f"missing diff.resources.{key}")
            continue
        for bucket in ("to_create", "to_update", "to_delete", "unchanged"):
            if bucket not in section:
                issues.append(f"missing diff.resources.{key}.{bucket}")
            elif not isinstance(section[bucket], list):
                issues.append(f"diff.resources.{key}.{bucket} must be a list")
    scope = diff.get("scope")
    if scope is not None:
        issues.extend(
            f"diff.scope: {issue}" for issue in validate_restore_scope(scope)
        )
    return issues


def diff_has_changes(diff: dict[str, Any]) -> bool:
    resources = diff.get("resources", {})
    for key in (
        *MIGRATION_ORDER,
        "application_segment_moves",
        "application_segment_shares",
        "policy_rule_order",
    ):
        section = resources.get(key, {})
        if section.get("to_create") or section.get("to_update") or section.get("to_delete"):
            return True
    return False


def preflight_restore(
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    diff: dict[str, Any],
    *,
    allow_failed_backups: bool = False,
) -> list[str]:
    issues = []
    issues.extend(f"source backup: {issue}" for issue in validate_backup(source_backup, strict=True))
    issues.extend(f"target backup: {issue}" for issue in validate_backup(target_backup, strict=True))
    issues.extend(f"diff: {issue}" for issue in validate_diff(diff))
    issues.extend(f"dependency order: {issue}" for issue in migration_order_issues())

    if source_backup.get("errors") and not allow_failed_backups:
        issues.append("source backup has endpoint errors; pass --allow-failed-backups to override")
    if target_backup.get("errors") and not allow_failed_backups:
        issues.append("target backup has endpoint errors; pass --allow-failed-backups to override")

    source_id = source_backup.get("meta", {}).get("customerId")
    target_id = target_backup.get("meta", {}).get("customerId")
    diff_source_id = diff.get("meta", {}).get("source", {}).get("customerId")
    diff_target_id = diff.get("meta", {}).get("target", {}).get("customerId")
    if diff_source_id and source_id and str(diff_source_id) != str(source_id):
        issues.append("diff source customerId does not match source backup")
    if diff_target_id and target_id and str(diff_target_id) != str(target_id):
        issues.append("diff target customerId does not match target backup")
    if isinstance(diff.get("scope"), dict):
        try:
            expected = compute_restore_diff(
                source_backup,
                target_backup,
                scope=scope_from_diff(diff),
            )
            if canonical_json(diff.get("resources")) != canonical_json(
                expected.get("resources")
            ):
                issues.append(
                    "selective diff changes do not match its persisted scope and restore inputs"
                )
        except CliError as error:
            issues.append(f"selective restore scope: {error}")
    return issues
