"""Deterministic, credential-free restore simulation."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Iterator

from zpa_backup_restore.core.catalog import MIGRATION_ORDER, RESOURCES
from zpa_backup_restore.core.diff import name_of
from zpa_backup_restore.core.mapping import IDMapper, seed_by_name, seed_identity_refs
from zpa_backup_restore.core.restore import clean_payload, policy_set_id_for_rule
from zpa_backup_restore.resources.application_segments import (
    application_move_path,
    application_share_path,
)
from zpa_backup_restore.resources.policy_rules import (
    policy_reorder_ids,
    policy_reorder_path,
    policy_rule_path,
)
from zpa_backup_restore.security import redact


DEFERRED_REFERENCE_PREFIX = "$planned:"
POLICY_DEPENDENCIES = (
    "policy_sets",
    "identity_references",
    "application_segments",
    "inspection_profiles",
    "cbi_profiles",
)


def _source_ids(backup: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for value in backup.get("resources", {}).values():
        records = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        for record in records:
            if isinstance(record, dict) and record.get("id") is not None:
                identifiers.add(str(record["id"]))
    return identifiers


def _walk_values(value: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_values(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f"{path}[{index}]")
        return
    yield path, value


def _reference_diagnostics(
    payload: dict[str, Any] | None,
    source_ids: set[str],
    mapper: IDMapper,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    deferred: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    mapped_targets = set(mapper.map.values())
    for path, value in _walk_values(payload or {}):
        text = str(value)
        if text.startswith(DEFERRED_REFERENCE_PREFIX):
            deferred.append({"path": path, "reference": text})
        elif text in source_ids and text not in mapped_targets:
            unresolved.append({"path": path, "sourceId": text})
    return deferred, unresolved


def _planned_reference(key: str, source_id: Any) -> str:
    return f"{DEFERRED_REFERENCE_PREFIX}{key}:{source_id}"


def _resource_path(customer_id: str, template: str, *, target_id: Any | None = None) -> str:
    values: dict[str, Any] = {"customer_id": customer_id}
    if target_id is not None:
        values["id"] = target_id
    return template.format(**values)


def _request_for_change(
    *,
    action: str,
    key: str,
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
    target_backup: dict[str, Any],
    target_customer_id: str,
    mapper: IDMapper,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build the request template or return a blocking reason."""
    target_id = target.get("id") if isinstance(target, dict) else None

    if key == "policy_rules":
        rule = source if action != "delete" else target
        if not isinstance(rule, dict):
            return None, "policy rule data is missing"
        policy_set_id = policy_set_id_for_rule(target_backup, target or source or {})
        if not policy_set_id:
            return None, "target policy set could not be resolved"
        if action == "create":
            payload = mapper.remap(clean_payload(source or {}, None, create=True))
            payload["policySetId"] = policy_set_id
            return {
                "method": "POST",
                "path": policy_rule_path(target_customer_id, policy_set_id),
                "body": payload,
            }, None
        if target_id is None:
            return None, "target policy rule ID is missing"
        if action == "update":
            payload = mapper.remap(
                clean_payload(source or {}, None, create=False, target_id=target_id)
            )
            payload["policySetId"] = policy_set_id
            payload["id"] = str(target_id)
            return {
                "method": "PUT",
                "path": policy_rule_path(target_customer_id, policy_set_id, str(target_id)),
                "body": payload,
            }, None
        return {
            "method": "DELETE",
            "path": policy_rule_path(
                target_customer_id,
                policy_set_id,
                str(target_id),
                version="v1",
            ),
            "body": None,
        }, None

    meta = RESOURCES[key]
    if action == "create":
        payload = mapper.remap(clean_payload(source or {}, meta, create=True))
        return {
            "method": meta.get("create_method", "POST"),
            "path": _resource_path(
                target_customer_id,
                meta.get("create_path") or meta["path"],
            ),
            "body": payload,
        }, None
    if target_id is None:
        return None, f"target {key} ID is missing"
    detail_path = (
        meta.get("update_path")
        if action == "update"
        else meta.get("delete_path")
    ) or meta.get("detail_path")
    if not detail_path:
        return None, f"resource {key} does not define a detail path"
    if action == "update":
        payload = mapper.remap(
            clean_payload(source or {}, meta, create=False, target_id=target_id)
        )
        return {
            "method": meta.get("update_method", "PUT"),
            "path": _resource_path(target_customer_id, detail_path, target_id=target_id),
            "body": payload,
        }, None
    return {
        "method": meta.get("delete_method", "DELETE"),
        "path": _resource_path(target_customer_id, detail_path, target_id=target_id),
        "body": None,
    }, None


def simulate_restore(
    diff: dict[str, Any],
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    *,
    allow_delete: bool,
    allow_high_impact: bool,
) -> dict[str, Any]:
    """Build the exact ordered request plan without credentials or HTTP calls."""
    target_customer_id = str(target_backup.get("meta", {}).get("customerId") or "")
    source_customer_id = str(source_backup.get("meta", {}).get("customerId") or "")
    known_source_ids = _source_ids(source_backup)
    mapper = IDMapper()
    seed_identity_refs(mapper, source_backup, target_backup)

    operations: list[dict[str, Any]] = []
    legacy_log: list[dict[str, Any]] = []
    skip_reasons: Counter[str] = Counter()
    sequence = 0

    def add_operation(
        *,
        action: str,
        key: str,
        source: dict[str, Any] | None,
        target: dict[str, Any] | None,
        safeguard_reason: str | None = None,
        request_override: dict[str, Any] | None = None,
        request_issue_override: str | None = None,
        dependencies_override: tuple[str, ...] | None = None,
        high_impact_override: bool | None = None,
    ) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        resource = source if isinstance(source, dict) else target if isinstance(target, dict) else {}
        meta = RESOURCES.get(key, {})
        name = name_of(resource, meta.get("name_field", "name"))
        if request_override is not None or request_issue_override is not None:
            request, request_issue = request_override, request_issue_override
        else:
            request, request_issue = _request_for_change(
                action=action,
                key=key,
                source=source,
                target=target,
                target_backup=target_backup,
                target_customer_id=target_customer_id,
                mapper=mapper,
            )
        raw_payload = request.get("body") if request else None
        deferred, unresolved = _reference_diagnostics(raw_payload, known_source_ids, mapper)
        request_path = str(request.get("path") or "") if request else ""
        if DEFERRED_REFERENCE_PREFIX in request_path:
            deferred.append({"path": "$.request.path", "reference": request_path})

        if request_issue:
            status = "blocked"
            reason = request_issue
        elif not target_customer_id:
            status = "blocked"
            reason = "target customer ID is missing"
        elif unresolved:
            status = "blocked"
            reason = f"{len(unresolved)} unresolved source ID reference(s)"
        elif safeguard_reason:
            status = "skipped"
            reason = safeguard_reason
            skip_reasons[reason] += 1
        else:
            status = "planned"
            reason = ""

        payload_status = "none"
        if raw_payload is not None:
            if unresolved:
                payload_status = "unresolved"
            elif deferred:
                payload_status = "deferred"
            else:
                payload_status = "complete"

        operation = {
            "sequence": sequence,
            "action": action.upper(),
            "resource": key,
            "name": name,
            "status": status,
            "reason": reason,
            "safeguardReason": safeguard_reason or "",
            "dependencies": list(
                dependencies_override
                if dependencies_override is not None
                else POLICY_DEPENDENCIES
                if key in {"policy_rules", "policy_rule_order"}
                else meta.get("depends_on", [])
            ),
            "highImpact": (
                bool(high_impact_override)
                if high_impact_override is not None
                else bool(meta.get("high_impact"))
            ),
            "sourceId": source.get("id") if isinstance(source, dict) else None,
            "targetId": target.get("id") if isinstance(target, dict) else None,
            "request": {
                "method": request.get("method"),
                "path": request.get("path"),
                "body": redact(raw_payload),
            } if request else None,
            "payloadStatus": payload_status,
            "deferredReferences": deferred,
            "unresolvedReferences": unresolved,
        }
        operations.append(operation)
        legacy_status = {"planned": "dry", "skipped": "skip", "blocked": "error"}[status]
        request_text = ""
        if request:
            request_text = f"{request['method']} {request['path']} payload={payload_status}"
        detail = reason or request_text
        legacy_log.append(
            {
                "action": action.upper(),
                "resource": key,
                "name": name,
                "status": legacy_status,
                "detail": detail,
            }
        )
        return operation

    seed_by_name(
        mapper,
        source_backup.get("resources", {}).get("policy_rules") or [],
        target_backup.get("resources", {}).get("policy_rules") or [],
        "name",
    )

    for key in MIGRATION_ORDER:
        section = diff.get("resources", {}).get(key, {})
        meta = RESOURCES.get(key)
        if meta:
            seed_by_name(
                mapper,
                source_backup.get("resources", {}).get(key) or [],
                target_backup.get("resources", {}).get(key) or [],
                meta["name_field"],
            )

        for source in section.get("to_create", []) or []:
            reason = None
            if meta and meta.get("high_impact") and not allow_high_impact:
                reason = "high-impact writes disabled"
            operation = add_operation(
                action="create",
                key=key,
                source=source,
                target=None,
                safeguard_reason=reason,
            )
            if operation["status"] == "planned" and source.get("id") is not None:
                mapper.add(source["id"], _planned_reference(key, source["id"]))

        for change in section.get("to_update", []) or []:
            source = change.get("source") or {}
            target = change.get("target") or {}
            reason = None
            if meta and meta.get("high_impact") and not allow_high_impact:
                reason = "high-impact writes disabled"
            add_operation(
                action="update",
                key=key,
                source=source,
                target=target,
                safeguard_reason=reason,
            )

    application_special_dependencies = (
        "microtenants",
        "segment_groups",
        "server_groups",
        "application_segments",
    )
    for key, path_builder, body_fields in (
        (
            "application_segment_moves",
            application_move_path,
            ("targetMicrotenantId", "targetSegmentGroupId", "targetServerGroupId"),
        ),
        (
            "application_segment_shares",
            application_share_path,
            ("shareToMicrotenants",),
        ),
    ):
        for change in (
            diff.get("resources", {}).get(key, {}).get("to_update", []) or []
        ):
            source = change.get("source") or {}
            target = change.get("target") or {}
            target_id = target.get("id")
            if target.get("_planned"):
                target_id = mapper.lookup(target_id)
            issue = str(source.get("_issue") or "")
            request = None
            if not issue and target_id is None:
                issue = "target Application Segment ID is missing"
            if not issue:
                payload = mapper.remap(
                    {field: source.get(field) for field in body_fields}
                )
                request = {
                    "method": "POST" if key.endswith("moves") else "PUT",
                    "path": path_builder(target_customer_id, target_id),
                    "body": payload,
                }
            add_operation(
                action="move" if key.endswith("moves") else "share",
                key=key,
                source=source,
                target=target,
                safeguard_reason=(
                    None if allow_high_impact else "high-impact writes disabled"
                ),
                request_override=request,
                request_issue_override=issue or None,
                dependencies_override=application_special_dependencies,
                high_impact_override=True,
            )

    for key in reversed(MIGRATION_ORDER):
        section = diff.get("resources", {}).get(key, {})
        meta = RESOURCES.get(key)
        for target in section.get("to_delete", []) or []:
            reason = None
            if meta and meta.get("high_impact") and not allow_high_impact:
                reason = "high-impact writes disabled"
            elif not allow_delete:
                reason = "deletes disabled"
            add_operation(
                action="delete",
                key=key,
                source=None,
                target=target,
                safeguard_reason=reason,
            )

    for change in (
        diff.get("resources", {})
        .get("policy_rule_order", {})
        .get("to_update", [])
        or []
    ):
        policy_type = str(change.get("source", {}).get("_policyTypeName") or "")
        policy_set_id = policy_set_id_for_rule(
            target_backup,
            {"_policyTypeName": policy_type},
        )
        request = None
        issue = None
        if not policy_set_id:
            issue = f"target policy set could not be resolved for {policy_type}"
        else:
            rule_ids = policy_reorder_ids(
                change,
                mapper.lookup,
                retain_target_extras=not allow_delete,
            )
            request = {
                "method": "PUT",
                "path": policy_reorder_path(target_customer_id, policy_set_id),
                "body": rule_ids,
            }
        add_operation(
            action="reorder",
            key="policy_rule_order",
            source=change.get("source"),
            target=change.get("target"),
            request_override=request,
            request_issue_override=issue,
            dependencies_override=POLICY_DEPENDENCIES,
        )

    planned = sum(operation["status"] == "planned" for operation in operations)
    skipped = sum(operation["status"] == "skipped" for operation in operations)
    blocked = sum(operation["status"] == "blocked" for operation in operations)
    deferred_operations = sum(operation["payloadStatus"] == "deferred" for operation in operations)
    deferred_references = sum(len(operation["deferredReferences"]) for operation in operations)
    unresolved_references = sum(len(operation["unresolvedReferences"]) for operation in operations)

    return {
        "kind": "restore-simulation",
        "schemaVersion": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": diff.get("scope"),
        "sourceCustomerId": source_customer_id,
        "targetCustomerId": target_customer_id,
        "safeguards": {
            "allowDelete": allow_delete,
            "allowHighImpact": allow_high_impact,
        },
        "summary": {
            "total": len(operations),
            "planned": planned,
            "skipped": skipped,
            "blocked": blocked,
            "deferredOperations": deferred_operations,
            "deferredReferences": deferred_references,
            "unresolvedReferences": unresolved_references,
        },
        "skipReasons": dict(sorted(skip_reasons.items())),
        "hasBlockingIssues": blocked > 0,
        "operations": operations,
        "ok": 0,
        "dry": planned,
        "errors": blocked,
        "skipped": skipped,
        "log": legacy_log,
    }


__all__ = ["DEFERRED_REFERENCE_PREFIX", "simulate_restore"]
