"""Guarded restore execution in dependency order."""

from __future__ import annotations

import copy
from typing import Any, Protocol

from zpa_backup_restore.core.catalog import MIGRATION_ORDER, RESOURCES, SYSTEM_FIELDS, WRITE_SKIP_FIELDS
from zpa_backup_restore.core.diff import name_of
from zpa_backup_restore.core.mapping import IDMapper, seed_by_name, seed_identity_refs
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources.application_segments import (
    application_move_path,
    application_share_path,
)
from zpa_backup_restore.resources.policy_rules import (
    policy_reorder_ids,
    policy_reorder_path,
    policy_rule_path,
)


class ZPAClient(Protocol):
    customer_id: str

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any: ...


class OperationJournal(Protocol):
    def begin(
        self,
        *,
        action: str,
        resource: str,
        name: str,
        source_id: Any | None,
        target_id: Any | None,
    ) -> None: ...

    def finish(
        self,
        *,
        action: str,
        resource: str,
        name: str,
        source_id: Any | None,
        target_id: Any | None,
        status: str,
        detail: str,
        created_target_id: Any | None = None,
    ) -> None: ...


def path_for(client: ZPAClient, template: str, **values: Any) -> str:
    return template.format(customer_id=client.customer_id, **values)


def status_label(status: str) -> str:
    return {
        "dry": "DRY-RUN",
        "ok": "OK",
        "skip": "SKIP",
        "error": "ERROR",
    }.get(status, status.upper())


def clean_payload(
    obj: dict[str, Any],
    meta: dict | None,
    *,
    create: bool,
    target_id: Any | None = None,
) -> dict[str, Any]:
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


def create_resource(client: ZPAClient, key: str, payload: dict[str, Any]) -> Any:
    meta = RESOURCES[key]
    return client.request(
        meta.get("create_method", "POST"),
        path_for(client, meta.get("create_path") or meta["path"]),
        body=payload,
    )


def update_resource(client: ZPAClient, key: str, target_id: Any, payload: dict[str, Any]) -> Any:
    meta = RESOURCES[key]
    detail_path = meta.get("update_path") or meta.get("detail_path")
    if not detail_path:
        raise CliError(f"Resource {key} does not define an update path")
    return client.request(
        meta.get("update_method", "PUT"),
        path_for(client, detail_path, id=target_id),
        body=payload,
    )


def delete_resource(client: ZPAClient, key: str, target_id: Any) -> Any:
    meta = RESOURCES[key]
    detail_path = meta.get("delete_path") or meta.get("detail_path")
    if not detail_path:
        raise CliError(f"Resource {key} does not define a delete path")
    return client.request(
        meta.get("delete_method", "DELETE"),
        path_for(client, detail_path, id=target_id),
    )


def policy_set_id_for_rule(backup: dict[str, Any], rule: dict[str, Any]) -> str | None:
    policy_type = rule.get("_policyTypeName") or rule.get("policyType")
    policy_sets = backup.get("resources", {}).get("policy_sets", {})
    if isinstance(policy_sets, dict) and policy_type in policy_sets:
        policy_set = policy_sets[policy_type]
        return str(policy_set.get("id") or policy_set.get("policySetId") or "")
    return str(rule.get("_policySetId") or rule.get("policySetId") or "") or None


def create_policy_rule(client: ZPAClient, target_backup: dict[str, Any], rule: dict[str, Any]) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {rule.get('name')}")
    payload = clean_payload(rule, None, create=True)
    payload["policySetId"] = policy_set_id
    return client.request("POST", policy_rule_path(client.customer_id, policy_set_id), body=payload)


def update_policy_rule(
    client: ZPAClient,
    target_backup: dict[str, Any],
    target_rule: dict[str, Any],
    payload: dict[str, Any],
) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, target_rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {target_rule.get('name')}")
    rule_id = str(target_rule.get("id"))
    payload["policySetId"] = policy_set_id
    payload["id"] = rule_id
    return client.request(
        "PUT",
        policy_rule_path(client.customer_id, policy_set_id, rule_id),
        body=payload,
    )


def delete_policy_rule(client: ZPAClient, target_backup: dict[str, Any], target_rule: dict[str, Any]) -> Any:
    policy_set_id = policy_set_id_for_rule(target_backup, target_rule)
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for rule {target_rule.get('name')}")
    return client.request(
        "DELETE",
        policy_rule_path(
            client.customer_id,
            policy_set_id,
            str(target_rule.get("id")),
            version="v1",
        ),
    )


def reorder_policy_rules(
    client: ZPAClient,
    target_backup: dict[str, Any],
    change: dict[str, Any],
    mapper: IDMapper,
    *,
    retain_target_extras: bool,
) -> Any:
    policy_type = str(change.get("source", {}).get("_policyTypeName") or "")
    policy_set_id = policy_set_id_for_rule(
        target_backup,
        {"_policyTypeName": policy_type},
    )
    if not policy_set_id:
        raise CliError(f"Could not resolve target policy set for {policy_type}")
    target_ids = {
        str(rule["id"])
        for rule in change.get("target", {}).get("rules", []) or []
        if rule.get("id") is not None
    }
    unresolved = [
        str(rule["id"])
        for rule in change.get("source", {}).get("rules", []) or []
        if rule.get("id") is not None
        and str(mapper.lookup(rule["id"])) == str(rule["id"])
        and str(rule["id"]) not in target_ids
    ]
    if unresolved:
        raise CliError(
            f"Could not resolve {len(unresolved)} destination rule ID(s) for {policy_type}"
        )
    rule_ids = policy_reorder_ids(
        change,
        mapper.lookup,
        retain_target_extras=retain_target_extras,
    )
    return client.request(
        "PUT",
        policy_reorder_path(client.customer_id, policy_set_id),
        body=rule_ids,
    )


def apply_application_segment_special(
    client: ZPAClient,
    key: str,
    change: dict[str, Any],
    mapper: IDMapper,
) -> Any:
    source = change.get("source") or {}
    target = change.get("target") or {}
    if source.get("_issue"):
        raise CliError(str(source["_issue"]))
    target_id = target.get("id")
    if target.get("_planned"):
        source_target_id = target_id
        target_id = mapper.lookup(target_id)
        if str(target_id) == str(source_target_id):
            raise CliError("Created Application Segment target ID is unresolved")
    if target_id is None:
        raise CliError("Target Application Segment ID is missing")
    if key == "application_segment_moves":
        fields = ("targetMicrotenantId", "targetSegmentGroupId", "targetServerGroupId")
        method = "POST"
        path = application_move_path(client.customer_id, target_id)
    else:
        fields = ("shareToMicrotenants",)
        method = "PUT"
        path = application_share_path(client.customer_id, target_id)
    raw_payload = {field: source.get(field) for field in fields}
    unresolved = [
        str(value)
        for value in raw_payload.values()
        if value not in (None, [])
        for value in (value if isinstance(value, list) else [value])
        if str(value) not in mapper.map
    ]
    if unresolved:
        raise CliError(f"Could not resolve {len(unresolved)} special-operation reference ID(s)")
    return client.request(method, path, body=mapper.remap(raw_payload))


def apply_diff(
    client: ZPAClient,
    diff: dict[str, Any],
    src_backup: dict[str, Any],
    tgt_backup: dict[str, Any],
    *,
    dry_run: bool,
    allow_delete: bool,
    allow_high_impact: bool,
    journal: OperationJournal | None = None,
) -> dict[str, Any]:
    """Apply a reviewed diff while enforcing restore safeguards."""
    mapper = IDMapper()
    seed_identity_refs(mapper, src_backup, tgt_backup)
    seed_by_name(
        mapper,
        src_backup.get("resources", {}).get("policy_rules") or [],
        tgt_backup.get("resources", {}).get("policy_rules") or [],
        "name",
    )
    result: dict[str, Any] = {"ok": 0, "dry": 0, "errors": 0, "skipped": 0, "log": []}

    def begin(
        action: str,
        key: str,
        name: str,
        source: dict[str, Any] | None,
        target: dict[str, Any] | None,
    ) -> None:
        if journal:
            journal.begin(
                action=action,
                resource=key,
                name=name,
                source_id=source.get("id") if source else None,
                target_id=target.get("id") if target else None,
            )

    def record(
        action: str,
        key: str,
        name: str,
        status: str,
        detail: str = "",
        *,
        source: dict[str, Any] | None = None,
        target: dict[str, Any] | None = None,
        created_target_id: Any | None = None,
    ) -> None:
        result["log"].append(
            {"action": action, "resource": key, "name": name, "status": status, "detail": detail}
        )
        counter = {"ok": "ok", "dry": "dry", "error": "errors"}.get(status, "skipped")
        result[counter] += 1
        if journal:
            journal.finish(
                action=action,
                resource=key,
                name=name,
                source_id=source.get("id") if source else None,
                target_id=target.get("id") if target else None,
                status=status,
                detail=detail,
                created_target_id=created_target_id,
            )
        print(f"{action:<7} {key:<22} {status_label(status):<7} {name} {detail}".rstrip())

    for key in MIGRATION_ORDER:
        section = diff.get("resources", {}).get(key, {})
        if key != "policy_rules":
            meta = RESOURCES[key]
            seed_by_name(
                mapper,
                src_backup["resources"].get(key) or [],
                tgt_backup["resources"].get(key) or [],
                meta["name_field"],
            )
            if meta.get("high_impact") and not allow_high_impact:
                for obj in section.get("to_create", []):
                    record("CREATE", key, name_of(obj, meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact", source=obj)
                for change in section.get("to_update", []):
                    record("UPDATE", key, name_of(change.get("source", {}), meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact", source=change.get("source"), target=change.get("target"))
                continue

        for obj in section.get("to_create", []):
            name = name_of(obj, "name")
            begin("CREATE", key, name, obj, None)
            try:
                if key == "policy_rules":
                    payload = mapper.remap(obj)
                    if dry_run:
                        record("CREATE", key, name, "dry", source=obj)
                    else:
                        created = create_policy_rule(client, tgt_backup, payload)
                        if isinstance(created, dict):
                            mapper.add(obj.get("id"), created.get("id"))
                        record("CREATE", key, name, "ok", source=obj, created_target_id=created.get("id") if isinstance(created, dict) else None)
                    continue
                payload = mapper.remap(clean_payload(obj, RESOURCES[key], create=True))
                if dry_run:
                    record("CREATE", key, name, "dry", source=obj)
                else:
                    created = create_resource(client, key, payload)
                    if isinstance(created, dict):
                        mapper.add(obj.get("id"), created.get("id"))
                    record("CREATE", key, name, "ok", source=obj, created_target_id=created.get("id") if isinstance(created, dict) else None)
            except CliError as error:
                record("CREATE", key, name, "error", str(error), source=obj)

        for change in section.get("to_update", []):
            source = change["source"]
            target = change["target"]
            name = name_of(source, "name")
            begin("UPDATE", key, name, source, target)
            try:
                payload = mapper.remap(
                    clean_payload(
                        source,
                        None if key == "policy_rules" else RESOURCES[key],
                        create=False,
                        target_id=target.get("id"),
                    )
                )
                if dry_run:
                    record("UPDATE", key, name, "dry", source=source, target=target)
                elif key == "policy_rules":
                    update_policy_rule(client, tgt_backup, target, payload)
                    mapper.add(source.get("id"), target.get("id"))
                    record("UPDATE", key, name, "ok", source=source, target=target)
                else:
                    update_resource(client, key, target.get("id"), payload)
                    mapper.add(source.get("id"), target.get("id"))
                    record("UPDATE", key, name, "ok", source=source, target=target)
            except CliError as error:
                record("UPDATE", key, name, "error", str(error), source=source, target=target)

    for key, action in (
        ("application_segment_moves", "MOVE"),
        ("application_segment_shares", "SHARE"),
    ):
        for change in (
            diff.get("resources", {}).get(key, {}).get("to_update", []) or []
        ):
            source = change.get("source") or {}
            target = change.get("target") or {}
            journal_target = target
            if target.get("_planned"):
                journal_target = copy.deepcopy(target)
                journal_target["id"] = mapper.lookup(target.get("id"))
            name = name_of(source, "name")
            if not allow_high_impact:
                record(
                    action,
                    key,
                    name,
                    "skip",
                    "high-impact resource; pass --allow-high-impact",
                    source=source,
                    target=journal_target,
                )
                continue
            begin(action, key, name, source, journal_target)
            try:
                if dry_run:
                    record(action, key, name, "dry", source=source, target=journal_target)
                else:
                    apply_application_segment_special(client, key, change, mapper)
                    record(action, key, name, "ok", source=source, target=journal_target)
            except CliError as error:
                record(
                    action,
                    key,
                    name,
                    "error",
                    str(error),
                    source=source,
                    target=journal_target,
                )

    for key in reversed(MIGRATION_ORDER):
        section = diff.get("resources", {}).get(key, {})
        if key != "policy_rules":
            meta = RESOURCES[key]
            if meta.get("high_impact") and not allow_high_impact:
                for obj in section.get("to_delete", []):
                    record("DELETE", key, name_of(obj, meta["name_field"]), "skip", "high-impact resource; pass --allow-high-impact", target=obj)
                continue

        for target in section.get("to_delete", []):
            name = name_of(target, "name")
            if not allow_delete:
                record("DELETE", key, name, "skip", "delete disabled", target=target)
                continue
            begin("DELETE", key, name, None, target)
            try:
                if dry_run:
                    record("DELETE", key, name, "dry", target=target)
                elif key == "policy_rules":
                    delete_policy_rule(client, tgt_backup, target)
                    record("DELETE", key, name, "ok", target=target)
                else:
                    delete_resource(client, key, target.get("id"))
                    record("DELETE", key, name, "ok", target=target)
            except CliError as error:
                record("DELETE", key, name, "error", str(error), target=target)

    order_changes = (
        diff.get("resources", {})
        .get("policy_rule_order", {})
        .get("to_update", [])
        or []
    )
    for change in order_changes:
        source = change.get("source") or {}
        target = change.get("target") or {}
        name = str(source.get("_policyTypeName") or source.get("name") or "policy")
        begin("REORDER", "policy_rule_order", name, source, target)
        try:
            if dry_run:
                record(
                    "REORDER",
                    "policy_rule_order",
                    name,
                    "dry",
                    source=source,
                    target=target,
                )
            else:
                reorder_policy_rules(
                    client,
                    tgt_backup,
                    change,
                    mapper,
                    retain_target_extras=not allow_delete,
                )
                record(
                    "REORDER",
                    "policy_rule_order",
                    name,
                    "ok",
                    source=source,
                    target=target,
                )
        except CliError as error:
            record(
                "REORDER",
                "policy_rule_order",
                name,
                "error",
                str(error),
                source=source,
                target=target,
            )

    print(
        "restore summary: "
        f"ok={result['ok']} dry-run={result['dry']} "
        f"skipped={result['skipped']} errors={result['errors']}"
    )
    return result


__all__ = [
    "IDMapper",
    "OperationJournal",
    "apply_diff",
    "apply_application_segment_special",
    "clean_payload",
    "create_policy_rule",
    "create_resource",
    "delete_policy_rule",
    "delete_resource",
    "path_for",
    "policy_set_id_for_rule",
    "reorder_policy_rules",
    "seed_by_name",
    "seed_identity_refs",
    "status_label",
    "update_policy_rule",
    "update_resource",
]
