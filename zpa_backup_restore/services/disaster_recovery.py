"""Credential-free disaster-recovery runbooks with auditable checklist state."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from zpa_backup_restore import __version__
from zpa_backup_restore.core.catalog import COVERAGE_RESOURCES, MIGRATION_ORDER
from zpa_backup_restore.core.integrity import (
    backup_digest,
    canonical_json,
    sha256_text,
    validate_backup,
)
from zpa_backup_restore.core.selection import SELECTABLE_RESOURCE_TYPES, canonical_selector
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.security import redact, redact_text
from zpa_backup_restore.services.snapshots import (
    build_inventory,
    sha256_file,
    tenant_fingerprint,
)


DR_RUNBOOK_KIND = "zpa-disaster-recovery-runbook"
DR_RUNBOOK_SCHEMA_VERSION = "1.0"
DR_CHECKLIST_STATUSES = ("pending", "completed", "blocked", "not-applicable")
DR_COMPLETION_STATUSES = ("completed", "not-applicable")
DR_CAPABILITIES = (
    "automated",
    "reference",
    "protected-manual",
    "audit-only",
    "external",
)

IDENTITY_RESOURCE_TYPES = (
    "idps",
    "saml_attributes",
    "scim_attributes",
    "scim_groups",
)

COVERAGE_MEMBERS = {
    "identity_references": IDENTITY_RESOURCE_TYPES,
    "policy_rules": ("policy_sets", "policy_rules"),
}

RESOURCE_COVERAGE_DOMAINS = {
    **{resource_type: "identity_references" for resource_type in IDENTITY_RESOURCE_TYPES},
    "policy_sets": "policy_rules",
}

PROTECTED_MANUAL_DOMAINS = {
    "business_continuity_settings",
    "private_clouds",
    "private_cloud_controller_groups",
}

KNOWN_EXTERNAL_RECOVERY_AREAS = (
    {
        "key": "live-app-connector-instances",
        "name": "Live App Connector instances",
        "instructions": (
            "Confirm the deployment inventory, hosting platform, network placement, version, and health outside this backup.",
            "Rebuild or re-enroll instances through the approved Zscaler and infrastructure procedure.",
            "Attach deployment and post-recovery health evidence.",
        ),
    },
    {
        "key": "live-private-service-edge-instances",
        "name": "Live Private Service Edge instances",
        "instructions": (
            "Confirm the Private Service Edge deployment inventory and infrastructure prerequisites outside this backup.",
            "Rebuild or re-enroll instances through the approved Zscaler and infrastructure procedure.",
            "Attach deployment, version, and service-health evidence.",
        ),
    },
    {
        "key": "certificates-and-private-keys",
        "name": "Certificates and private keys",
        "instructions": (
            "Retrieve certificates and private keys from the approved certificate or secrets-management system; they are intentionally excluded from backups.",
            "Install or rotate them through the supported administrative workflow without placing secret material in this runbook.",
            "Record only a vault, change-ticket, or certificate fingerprint reference as evidence.",
        ),
    },
    {
        "key": "provisioning-keys",
        "name": "Provisioning keys",
        "instructions": (
            "Generate or retrieve provisioning keys through the supported administrative workflow; keys are intentionally not backed up.",
            "Enroll the required components and verify their connected state.",
            "Record a non-secret ticket or asset reference as evidence.",
        ),
    },
    {
        "key": "privileged-credentials",
        "name": "Privileged credentials and other secrets",
        "instructions": (
            "Recover privileged credentials from the separately controlled secrets-management process.",
            "Rotate credentials when exposure or loss is possible and validate least-privilege access.",
            "Record only a non-secret vault or change reference as evidence.",
        ),
    },
    {
        "key": "tenant-administration",
        "name": "Tenant administration and lifecycle configuration",
        "instructions": (
            "Review tenant administration, role assignment, subscription, and lifecycle settings that are outside generic configuration cloning.",
            "Recreate required settings through the supported administrative process.",
            "Attach an approved administrative export, ticket, or independent review as evidence.",
        ),
    },
)

MUTABLE_ITEM_FIELDS = (
    "status",
    "operator",
    "updatedAt",
    "completedAt",
    "evidence",
    "operatorNote",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _command(arguments: Iterable[str | Path]) -> str:
    return shlex.join([str(argument) for argument in arguments])


def _resource_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return len(value)
    return 1 if value else 0


def _coverage_domain(resource_type: str) -> str:
    return RESOURCE_COVERAGE_DOMAINS.get(resource_type, resource_type)


def _coverage_capability(resource_type: str, meta: dict[str, Any]) -> str:
    if resource_type in SELECTABLE_RESOURCE_TYPES and meta.get("writable"):
        return "automated"
    if meta.get("mode") == "reference":
        return "reference"
    if resource_type in PROTECTED_MANUAL_DOMAINS:
        return "protected-manual"
    if meta.get("mode") == "audit":
        return "audit-only"
    return "external"


def _resource_metadata(resource_type: str) -> tuple[str, dict[str, Any]]:
    domain = _coverage_domain(resource_type)
    meta = COVERAGE_RESOURCES.get(domain)
    if isinstance(meta, dict):
        return domain, meta
    return domain, {
        "mode": "excluded",
        "sensitivity": "sensitive",
        "writable": False,
        "high_impact": False,
        "depends_on": [],
        "operations": [],
        "notes": "Resource was present in the backup but is not modeled by this application version.",
    }


def _risk(meta: dict[str, Any], *, high_impact: bool = False) -> str:
    sensitivity = str(meta.get("sensitivity") or "normal")
    if high_impact or meta.get("high_impact") or sensitivity in {"high-impact", "secret"}:
        return "high"
    if sensitivity == "sensitive":
        return "sensitive"
    return "normal"


def _new_item(
    *,
    item_id: str,
    sequence: int,
    phase: str,
    category: str,
    name: str,
    capability: str,
    instructions: Iterable[str],
    commands: Iterable[dict[str, str]] = (),
    resource_type: str = "",
    stable_key: str = "",
    mode: str = "",
    risk: str = "normal",
    dependencies: Iterable[str] = (),
    source_config_sha256: str = "",
    coverage_gap: bool = False,
    initial_status: str = "pending",
    detail: str = "",
) -> dict[str, Any]:
    if capability not in DR_CAPABILITIES:
        raise ValueError(f"Unsupported DR capability: {capability}")
    if initial_status not in DR_CHECKLIST_STATUSES:
        raise ValueError(f"Unsupported initial DR status: {initial_status}")
    return {
        "id": item_id,
        "sequence": sequence,
        "phase": phase,
        "category": category,
        "name": name,
        "resourceType": resource_type,
        "stableKey": stable_key,
        "mode": mode,
        "capability": capability,
        "risk": risk,
        "required": True,
        "coverageGap": coverage_gap,
        "dependencies": list(dependencies),
        "sourceConfigSha256": source_config_sha256,
        "detail": detail,
        "instructions": list(instructions),
        "commands": list(commands),
        "initialStatus": initial_status,
        "status": initial_status,
        "operator": "",
        "updatedAt": "",
        "completedAt": "",
        "evidence": "",
        "operatorNote": "",
    }


def _automated_instructions(high_impact: bool) -> tuple[str, ...]:
    impact_step = (
        "Obtain explicit approval for high-impact operations and enable them only in the reviewed simulation and restore commands."
        if high_impact
        else "Keep deletes and high-impact writes disabled unless the approved recovery scope explicitly requires them."
    )
    return (
        "Inspect the captured identity, dependencies, and configuration hash below.",
        "Run the exact selective restore-plan command and confirm the Destination customer before continuing.",
        "Validate and preflight the generated backup/diff set, then run the exact simulation command printed by the tool.",
        impact_step,
        "Review every planned, skipped, and blocked operation; do not continue while blockers or unexpected skips remain.",
        "Run the exact reviewed restore command printed by simulation.",
        "Confirm the post-restore residual diff for this scope is empty or formally accepted, then attach the result, report, journal, and run ID as evidence.",
    )


def _manual_instructions(capability: str) -> tuple[str, ...]:
    if capability == "reference":
        return (
            "Confirm the same named reference exists in the Destination tenant or recreate it through its authoritative administration process.",
            "Run simulation for dependent settings and verify that this reference maps unambiguously with no unresolved field paths.",
            "Attach an approved export, screenshot, ticket, or independent verification as evidence.",
        )
    if capability == "protected-manual":
        return (
            "Review the sanitized source metadata and identify secret or association data that is intentionally absent.",
            "Recover the setting through the supported Zscaler procedure with separately controlled secrets and approvals; generic restore is disabled.",
            "Verify associations and service behavior independently, then attach only non-secret evidence.",
        )
    if capability == "audit-only":
        return (
            "Decide whether this operational state must be recreated for the recovery scenario; it is not generic clone configuration.",
            "Use the supported operational or infrastructure procedure when recreation is required.",
            "Verify health, activation, time-window, or runtime state as applicable and attach non-secret evidence.",
        )
    return (
        "Identify the authoritative recovery process because this setting is not automatically restorable by this tool.",
        "Recover and independently verify the setting through the approved platform or administrative procedure.",
        "Attach a non-secret export, ticket, screenshot, or test result as evidence.",
    )


def _domain_capture(
    domain: str,
    meta: dict[str, Any],
    resources: dict[str, Any],
    endpoint_errors: set[str],
) -> dict[str, Any]:
    members = COVERAGE_MEMBERS.get(domain, (domain,))
    captured_members = [member for member in members if member in resources]
    failed_members = [
        member
        for member in members
        if member in endpoint_errors or domain in endpoint_errors
    ]
    counts = {
        member: _resource_count(resources.get(member))
        for member in members
        if member in resources
    }
    if failed_members:
        status = "failed"
    elif captured_members:
        status = "captured"
    elif meta.get("optional"):
        status = "optional-not-present"
    else:
        status = "missing"
    return {
        "resource": domain,
        "members": list(members),
        "capturedMembers": captured_members,
        "failedMembers": failed_members,
        "counts": counts,
        "objectCount": sum(count for count in counts.values() if isinstance(count, int)),
        "captureStatus": status,
        "mode": meta.get("mode", "reference"),
        "sensitivity": meta.get("sensitivity", "normal"),
        "capability": _coverage_capability(domain, meta),
        "dependencies": list(meta.get("depends_on", [])),
        "notes": str(meta.get("notes") or ""),
        "operationCount": len(meta.get("operations", []) or []),
    }


def _plan_projection(runbook: dict[str, Any]) -> dict[str, Any]:
    immutable_items = []
    for item in runbook.get("items", []) or []:
        immutable_items.append(
            {
                key: value
                for key, value in item.items()
                if key not in MUTABLE_ITEM_FIELDS
            }
        )
    return {
        "kind": runbook.get("kind"),
        "schemaVersion": runbook.get("schemaVersion"),
        "title": runbook.get("title"),
        "createdAt": runbook.get("createdAt"),
        "applicationVersion": runbook.get("applicationVersion"),
        "source": runbook.get("source"),
        "coverage": runbook.get("coverage"),
        "items": immutable_items,
    }


def _state_projection(runbook: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            **{field: item.get(field, "") for field in MUTABLE_ITEM_FIELDS},
        }
        for item in runbook.get("items", []) or []
    ]


def summarize_runbook(runbook: dict[str, Any]) -> dict[str, Any]:
    items = runbook.get("items", []) or []
    statuses = Counter(str(item.get("status") or "pending") for item in items)
    capabilities = Counter(str(item.get("capability") or "external") for item in items)
    categories = Counter(str(item.get("category") or "unknown") for item in items)
    addressed = statuses["completed"] + statuses["not-applicable"]
    total = len(items)
    required = [item for item in items if item.get("required", True)]
    required_addressed = sum(
        1 for item in required if item.get("status") in DR_COMPLETION_STATUSES
    )
    return {
        "total": total,
        "pending": statuses["pending"],
        "completed": statuses["completed"],
        "blocked": statuses["blocked"],
        "notApplicable": statuses["not-applicable"],
        "addressed": addressed,
        "completionPercent": round((addressed / total) * 100, 1) if total else 100.0,
        "allRequiredAddressed": required_addressed == len(required),
        "settingItems": categories["setting"],
        "domainItems": categories["domain"],
        "externalGapItems": categories["external-gap"],
        "backupIssueItems": categories["backup-issue"],
        "capabilities": {
            capability: capabilities[capability]
            for capability in DR_CAPABILITIES
        },
    }


def _refresh_integrity(runbook: dict[str, Any]) -> None:
    runbook["summary"] = summarize_runbook(runbook)
    events = runbook.get("auditTrail", []) or []
    runbook["integrity"] = {
        "planSha256": sha256_text(canonical_json(_plan_projection(runbook))),
        "stateSha256": sha256_text(canonical_json(_state_projection(runbook))),
        "auditHeadSha256": str(events[-1].get("eventHash") or "") if events else "",
        "auditEventCount": len(events),
    }


def build_disaster_recovery_runbook(
    backup: dict[str, Any],
    source_path: Path,
    *,
    command_prefix: Iterable[str | Path] = ("python3", "-m", "zpa_backup_restore"),
    title: str = "ZPA Disaster Recovery Runbook",
    clock: Callable[[], str] = _now,
) -> dict[str, Any]:
    """Build a complete runbook without tenant credentials or network calls."""
    if not isinstance(backup, dict):
        raise CliError("Backup root must be a JSON object")
    resources = backup.get("resources")
    if not isinstance(resources, dict):
        raise CliError("Cannot build a DR runbook: backup is missing its resources object")
    if not source_path.is_file():
        raise CliError(f"Backup artifact does not exist: {source_path}")

    created_at = clock()
    validation_issues = validate_backup(backup, strict=True)
    endpoint_errors = {
        str(key) for key in (backup.get("errors", {}) or {})
    }
    content_sha256 = backup_digest(backup)
    inventory, references = build_inventory(content_sha256, backup)
    reference_index: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for reference in references:
        target = f"{reference.target_resource_type}/{reference.target_stable_key}"
        reference_index[
            (reference.from_resource_type, reference.from_stable_key)
        ].append(target)

    resolved_source = source_path.resolve()
    prefix = [str(value) for value in command_prefix]
    validate_command = _command(
        [*prefix, "validate", "--backup", resolved_source, "--strict-manifest"]
    )
    source_meta = backup.get("meta", {}) if isinstance(backup.get("meta"), dict) else {}
    customer_id = str(source_meta.get("customerId") or "")
    manifest = backup.get("manifest", {}) if isinstance(backup.get("manifest"), dict) else {}

    coverage = [
        _domain_capture(domain, meta, resources, endpoint_errors)
        for domain, meta in COVERAGE_RESOURCES.items()
    ]
    coverage_domains = {entry["resource"] for entry in coverage}
    for resource_type in sorted(resources):
        domain = _coverage_domain(resource_type)
        if domain not in coverage_domains and resource_type not in {"policy_sets"}:
            coverage.append(
                {
                    "resource": domain,
                    "members": [resource_type],
                    "capturedMembers": [resource_type],
                    "failedMembers": [],
                    "counts": {resource_type: _resource_count(resources[resource_type])},
                    "objectCount": _resource_count(resources[resource_type]) or 0,
                    "captureStatus": "unmodeled",
                    "mode": "excluded",
                    "sensitivity": "sensitive",
                    "capability": "external",
                    "dependencies": [],
                    "notes": "Present in the backup but not modeled by this application version.",
                    "operationCount": 0,
                }
            )
            coverage_domains.add(domain)

    items: list[dict[str, Any]] = []

    def append_item(**kwargs: Any) -> None:
        items.append(_new_item(sequence=len(items) + 1, **kwargs))

    readiness_blocked = bool(validation_issues or endpoint_errors)
    append_item(
        item_id="readiness.backup-integrity",
        phase="1-readiness",
        category="readiness",
        name="Verify backup integrity and capture completeness",
        capability="external",
        initial_status="blocked" if readiness_blocked else "pending",
        coverage_gap=readiness_blocked,
        detail=(
            f"{len(validation_issues)} validation issue(s); "
            f"{len(endpoint_errors)} endpoint error(s)."
        ),
        instructions=(
            "Run strict validation against the exact retained backup artifact.",
            "Review every validation issue, endpoint error, warning, manifest count, and coverage-domain status in this runbook.",
            "Do not start recovery until missing or failed capture areas have an approved external recovery path.",
        ),
        commands=({"label": "Strict backup validation", "command": validate_command},),
    )
    append_item(
        item_id="readiness.destination-control",
        phase="1-readiness",
        category="readiness",
        name="Verify Destination tenant and administrative access",
        capability="external",
        instructions=(
            "Confirm the Destination customer ID, tenant name, subscription, API access, and emergency administrative access with two operators.",
            "Ensure Source credentials are not entered as Destination credentials unless restoring that exact tenant is explicitly approved.",
            "Record the incident, change, or recovery authorization and the independently verified Destination identity.",
        ),
    )
    append_item(
        item_id="readiness.infrastructure",
        phase="1-readiness",
        category="readiness",
        name="Verify external infrastructure and secret recovery",
        capability="external",
        instructions=(
            "Confirm DNS, network paths, connector/service-edge hosting, certificate services, identity systems, secret stores, and time synchronization are available.",
            "Confirm off-machine copies of the desired backup, runbook, and required external recovery material are accessible.",
            "Record the infrastructure readiness decision and evidence.",
        ),
    )
    append_item(
        item_id="governance.change-control",
        phase="2-authorization",
        category="authorization",
        name="Approve recovery scope, safeguards, and maintenance window",
        capability="external",
        risk="high",
        instructions=(
            "Approve the Destination tenant, recovery point, setting scope, expected business impact, operators, and maintenance window.",
            "Decide separately whether deletes, high-impact writes, incomplete backups, or preflight bypasses are permitted.",
            "Record approver, incident/change reference, communication plan, and rollback decision.",
        ),
    )

    domain_order = [
        *MIGRATION_ORDER,
        *sorted(domain for domain in coverage_domains if domain not in MIGRATION_ORDER),
    ]
    coverage_by_domain = {entry["resource"]: entry for entry in coverage}
    for domain in domain_order:
        entry = coverage_by_domain.get(domain)
        if not entry:
            continue
        capture_status = entry["captureStatus"]
        initial_status = "blocked" if capture_status in {"failed", "missing", "unmodeled"} else "pending"
        capability = str(entry["capability"])
        meta = COVERAGE_RESOURCES.get(domain, {})
        whole_domain_command = ""
        if domain in SELECTABLE_RESOURCE_TYPES and capability == "automated":
            whole_domain_command = _command(
                [
                    *prefix,
                    "restore-plan",
                    "--source-backup",
                    resolved_source,
                    "--select-resource",
                    domain,
                ]
            )
        instructions = [
            f"Confirm the {domain} capture status is {capture_status} and the recorded object count is {entry['objectCount']}.",
        ]
        if capture_status == "captured" and entry["objectCount"] == 0:
            instructions.append(
                "Confirm that zero source objects is intentional and review the Destination for surplus objects; deletes remain disabled by default."
            )
        elif capture_status in {"failed", "missing", "unmodeled"}:
            instructions.append(
                "Resolve the capture gap or approve and document an authoritative external recovery source before this domain is signed off."
            )
        if capability == "automated":
            instructions.append(
                "Complete and evidence every per-setting item in this domain; use the whole-domain command only when that broader scope is explicitly approved."
            )
        else:
            instructions.extend(_manual_instructions(capability)[:2])
        commands = (
            [{"label": "Plan complete resource domain", "command": whole_domain_command}]
            if whole_domain_command
            else []
        )
        append_item(
            item_id=f"domain.{domain}",
            phase="3-settings",
            category="domain",
            name=f"Domain sign-off: {domain}",
            resource_type=domain,
            mode=str(entry["mode"]),
            capability=capability,
            risk=_risk(meta),
            dependencies=entry["dependencies"],
            coverage_gap=initial_status == "blocked",
            initial_status=initial_status,
            detail=str(entry["notes"]),
            instructions=instructions,
            commands=commands,
        )

    resource_order = {key: index for index, key in enumerate(MIGRATION_ORDER)}
    inventory.sort(
        key=lambda resource: (
            resource_order.get(resource.resource_type, len(resource_order)),
            resource.resource_type,
            resource.stable_key,
            resource.display_name,
        )
    )
    for resource in inventory:
        domain, meta = _resource_metadata(resource.resource_type)
        capability = _coverage_capability(domain, meta)
        if resource.resource_type == "policy_sets":
            capability = "reference"
        ambiguous = "#duplicate-" in resource.stable_key
        selectable = (
            resource.writable
            and resource.resource_type in SELECTABLE_RESOURCE_TYPES
            and not ambiguous
        )
        if selectable:
            capability = "automated"
        elif ambiguous:
            capability = "external"
        selector = (
            canonical_selector(resource.resource_type, resource.stable_key)
            if selectable
            else ""
        )
        restore_command = (
            _command(
                [
                    *prefix,
                    "restore-plan",
                    "--source-backup",
                    resolved_source,
                    "--select",
                    selector,
                ]
            )
            if selector
            else ""
        )
        dependencies = sorted(
            set(meta.get("depends_on", []))
            | set(reference_index[(resource.resource_type, resource.stable_key)])
        )
        high_impact = bool(resource.high_impact or _risk(meta) == "high")
        if capability == "automated":
            instructions = _automated_instructions(high_impact)
            commands = [{"label": "Build selective restore plan", "command": restore_command}]
        else:
            instructions = _manual_instructions(capability)
            commands = []
        detail = str(meta.get("notes") or "")
        if ambiguous:
            detail = (
                "Stable identity is duplicated in the backup. Resolve the duplicate "
                "manually before attempting a selective restore."
            )
        append_item(
            item_id=(
                f"setting.{resource.resource_type}."
                f"{_short_hash(resource.resource_type + ':' + resource.stable_key)}"
            ),
            phase="3-settings",
            category="setting",
            name=resource.display_name,
            resource_type=resource.resource_type,
            stable_key=resource.stable_key,
            mode=(
                "reference"
                if resource.resource_type == "policy_sets"
                else str(meta.get("mode") or "excluded")
            ),
            capability=capability,
            risk=_risk(meta, high_impact=resource.high_impact),
            dependencies=dependencies,
            source_config_sha256=resource.config_sha256,
            coverage_gap=ambiguous or domain not in COVERAGE_RESOURCES,
            initial_status="blocked" if ambiguous else "pending",
            detail=detail,
            instructions=instructions,
            commands=commands,
        )

    for error_key in sorted(endpoint_errors):
        append_item(
            item_id=f"backup-error.{_short_hash(error_key)}",
            phase="3-settings",
            category="backup-issue",
            name=f"Resolve backup endpoint error: {error_key}",
            resource_type=error_key,
            mode="unknown",
            capability="external",
            risk="high",
            coverage_gap=True,
            initial_status="blocked",
            detail="The backup recorded an endpoint failure, so the affected settings may be absent.",
            instructions=(
                "Review the sanitized HTTP audit log and determine which settings were not captured.",
                "Repeat the backup successfully or obtain an authoritative approved export for the missing area.",
                "Rebuild the runbook from the corrected backup or attach the external recovery and verification evidence.",
            ),
        )

    for area in KNOWN_EXTERNAL_RECOVERY_AREAS:
        append_item(
            item_id=f"external.{area['key']}",
            phase="4-external",
            category="external-gap",
            name=str(area["name"]),
            mode="excluded",
            capability="external",
            risk="high" if "key" in area["key"] or "credential" in area["key"] else "sensitive",
            coverage_gap=True,
            detail="This area is intentionally outside generic backup/restore coverage.",
            instructions=area["instructions"],
        )

    append_item(
        item_id="verification.residual-diff",
        phase="5-verification",
        category="verification",
        name="Verify post-restore snapshot and residual differences",
        capability="external",
        instructions=(
            "Review the post-restore destination snapshot, execution journal, restore result, and residual diff/report.",
            "Require an empty expected scope or document every intentionally retained difference with approval.",
            "Attach the artifact paths, hashes, and run ID as evidence.",
        ),
    )
    append_item(
        item_id="verification.references-and-order",
        phase="5-verification",
        category="verification",
        name="Verify references, policy order, and high-impact associations",
        capability="external",
        instructions=(
            "Verify cross-tenant reference mappings and the final evaluation order of every restored policy type.",
            "Verify Microtenant placement, Application Segment move/share state, and other high-impact associations when used.",
            "Attach independent API, portal, or report evidence.",
        ),
    )
    append_item(
        item_id="verification.business-services",
        phase="5-verification",
        category="verification",
        name="Validate business services end to end",
        capability="external",
        instructions=(
            "Test representative application access, policy outcomes, PRA sessions, AppProtection behavior, logging, and connector/service-edge health.",
            "Confirm monitoring and incident communications show the expected recovered state.",
            "Record test cases, operator, timestamp, result, and exceptions.",
        ),
    )
    append_item(
        item_id="verification.audit-ledger",
        phase="5-verification",
        category="verification",
        name="Verify and archive audit evidence",
        capability="external",
        instructions=(
            "Run the audit ledger verification and inspect every recovery run, safeguard selection, artifact hash, and failure.",
            "Archive the runbook JSON/HTML, backup, plan, simulation, journals, pre/post snapshots, residual report, HTTP logs, ledger, and ledger checkpoint together.",
            "Record the final ledger head hash in a separately controlled system when stronger evidence is required.",
        ),
        commands=(
            {
                "label": "Verify run audit ledger",
                "command": _command([*prefix, "audit", "verify"]),
            },
        ),
    )
    append_item(
        item_id="closure.recovery-acceptance",
        phase="6-closure",
        category="closure",
        name="Approve recovery completion and follow-up actions",
        capability="external",
        risk="high",
        instructions=(
            "Confirm every required checklist item is completed or has an approved evidence-backed not-applicable decision.",
            "Record unresolved risks, temporary controls, owner, due date, and the final business acceptance decision.",
            "Retain the recovery package according to policy and schedule a post-incident review.",
        ),
    )

    runbook = {
        "kind": DR_RUNBOOK_KIND,
        "schemaVersion": DR_RUNBOOK_SCHEMA_VERSION,
        "title": title,
        "createdAt": created_at,
        "updatedAt": created_at,
        "applicationVersion": __version__,
        "source": {
            "artifactPath": str(resolved_source),
            "artifactSha256": sha256_file(source_path),
            "contentSha256": content_sha256,
            "manifestSha256": str(manifest.get("sha256") or ""),
            "schemaVersion": str(manifest.get("schemaVersion") or "unknown"),
            "capturedAt": str(source_meta.get("timestamp") or ""),
            "tenantLabel": str(source_meta.get("label") or "tenant"),
            "tenantFingerprint": tenant_fingerprint(customer_id),
            "customerHint": customer_id[-4:] if customer_id else "",
            "encrypted": source_path.name.endswith(".enc"),
            "validationIssues": redact(validation_issues),
            "endpointErrorKeys": sorted(endpoint_errors),
        },
        "coverage": {
            "modeledDomainCount": len(COVERAGE_RESOURCES),
            "explicitOperationCount": sum(
                len(meta.get("operations", []) or [])
                for meta in COVERAGE_RESOURCES.values()
            ),
            "domains": coverage,
            "knownExternalAreas": [
                {"key": area["key"], "name": area["name"]}
                for area in KNOWN_EXTERNAL_RECOVERY_AREAS
            ],
            "claim": (
                "Complete for every object captured in this backup and every "
                "modeled or explicitly known excluded area; not a claim of "
                "complete coverage for future or unmodeled ZPA APIs."
            ),
        },
        "items": items,
        "auditTrail": [],
    }
    _refresh_integrity(runbook)
    return runbook


def _event_hash(event: dict[str, Any]) -> str:
    unsigned = dict(event)
    unsigned.pop("eventHash", None)
    return sha256_text(canonical_json(unsigned))


def _derived_item_states(
    runbook: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str], str]:
    errors: list[str] = []
    states: dict[str, dict[str, Any]] = {}
    for item in runbook.get("items", []) or []:
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append("checklist item is missing an ID")
            continue
        if item_id in states:
            errors.append(f"duplicate checklist item ID: {item_id}")
            continue
        initial_status = str(item.get("initialStatus") or "")
        if initial_status not in DR_CHECKLIST_STATUSES:
            errors.append(f"{item_id}: invalid initial status {initial_status!r}")
        states[item_id] = {
            "status": initial_status,
            "operator": "",
            "updatedAt": "",
            "completedAt": "",
            "evidence": "",
            "operatorNote": "",
        }

    previous_hash = "0" * 64
    for index, event in enumerate(runbook.get("auditTrail", []) or [], start=1):
        if not isinstance(event, dict):
            errors.append(f"audit event {index} must be an object")
            continue
        if event.get("sequence") != index:
            errors.append(f"audit event {index}: sequence mismatch")
        if event.get("previousHash") != previous_hash:
            errors.append(f"audit event {index}: previous hash mismatch")
        calculated_hash = _event_hash(event)
        if event.get("eventHash") != calculated_hash:
            errors.append(f"audit event {index}: event hash mismatch")
        previous_hash = str(event.get("eventHash") or calculated_hash)
        item_id = str(event.get("itemId") or "")
        state = states.get(item_id)
        if state is None:
            errors.append(f"audit event {index}: unknown item {item_id!r}")
            continue
        if event.get("fromStatus") != state["status"]:
            errors.append(f"audit event {index}: previous item status mismatch")
        status = str(event.get("toStatus") or "")
        if status not in DR_CHECKLIST_STATUSES:
            errors.append(f"audit event {index}: invalid status {status!r}")
            continue
        timestamp = str(event.get("timestamp") or "")
        state.update(
            {
                "status": status,
                "operator": str(event.get("operator") or ""),
                "updatedAt": timestamp,
                "completedAt": timestamp if status in DR_COMPLETION_STATUSES else "",
                "evidence": str(event.get("evidence") or ""),
                "operatorNote": str(event.get("note") or ""),
            }
        )
    return states, errors, "" if previous_hash == "0" * 64 else previous_hash


def verify_disaster_recovery_runbook(
    runbook: dict[str, Any],
    *,
    check_source: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(runbook, dict):
        return {"valid": False, "errors": ["runbook root must be an object"]}
    if runbook.get("kind") != DR_RUNBOOK_KIND:
        errors.append(f"unsupported runbook kind {runbook.get('kind')!r}")
    if runbook.get("schemaVersion") != DR_RUNBOOK_SCHEMA_VERSION:
        errors.append(f"unsupported runbook schemaVersion {runbook.get('schemaVersion')!r}")
    items = runbook.get("items")
    if not isinstance(items, list):
        errors.append("runbook items must be a list")
        items = []
    for sequence, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"checklist item {sequence} must be an object")
            continue
        if item.get("sequence") != sequence:
            errors.append(f"checklist item {sequence}: sequence mismatch")
        if item.get("status") not in DR_CHECKLIST_STATUSES:
            errors.append(f"checklist item {sequence}: invalid status")

    integrity = runbook.get("integrity")
    if not isinstance(integrity, dict):
        errors.append("runbook integrity metadata is missing")
        integrity = {}
    expected_plan = sha256_text(canonical_json(_plan_projection(runbook)))
    if integrity.get("planSha256") != expected_plan:
        errors.append("runbook plan SHA-256 mismatch")

    states, audit_errors, audit_head = _derived_item_states(runbook)
    errors.extend(audit_errors)
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        derived = states.get(item_id)
        if derived is None:
            continue
        for field in MUTABLE_ITEM_FIELDS:
            if item.get(field, "") != derived[field]:
                errors.append(f"{item_id}: checklist state does not match audit trail")
                break

    expected_state = sha256_text(canonical_json(_state_projection(runbook)))
    if integrity.get("stateSha256") != expected_state:
        errors.append("runbook checklist state SHA-256 mismatch")
    if integrity.get("auditHeadSha256") != audit_head:
        errors.append("runbook audit head SHA-256 mismatch")
    if integrity.get("auditEventCount") != len(runbook.get("auditTrail", []) or []):
        errors.append("runbook audit event count mismatch")
    if runbook.get("summary") != summarize_runbook(runbook):
        errors.append("runbook summary does not match checklist state")

    source_status = "not-checked"
    if check_source:
        source = runbook.get("source", {}) if isinstance(runbook.get("source"), dict) else {}
        source_path = Path(str(source.get("artifactPath") or ""))
        if not source_path.is_file():
            errors.append(f"source backup artifact is missing: {source_path}")
            source_status = "missing"
        elif sha256_file(source_path) != source.get("artifactSha256"):
            errors.append(f"source backup artifact SHA-256 mismatch: {source_path}")
            source_status = "mismatch"
        else:
            source_status = "verified"
    return {
        "valid": not errors,
        "schemaVersion": runbook.get("schemaVersion"),
        "runbookId": expected_plan,
        "itemCount": len(items),
        "auditEventCount": len(runbook.get("auditTrail", []) or []),
        "auditHeadSha256": audit_head,
        "sourceArtifact": source_status,
        "summary": summarize_runbook(runbook),
        "errors": errors,
    }


def resolve_checklist_item(runbook: dict[str, Any], identifier: str) -> dict[str, Any]:
    identifier = identifier.strip()
    items = [
        item for item in runbook.get("items", []) or []
        if isinstance(item, dict)
    ]
    exact = [item for item in items if item.get("id") == identifier]
    if exact:
        return exact[0]
    matches = [item for item in items if str(item.get("id") or "").startswith(identifier)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise CliError(f"DR checklist item prefix is ambiguous: {identifier}")
    raise CliError(f"DR checklist item not found: {identifier}")


def update_disaster_recovery_checklist(
    runbook: dict[str, Any],
    *,
    item_identifier: str,
    status: str,
    operator: str,
    evidence: str = "",
    note: str = "",
    clock: Callable[[], str] = _now,
) -> dict[str, Any]:
    verification = verify_disaster_recovery_runbook(runbook, check_source=False)
    if not verification["valid"]:
        raise CliError(
            "Refusing to update an invalid DR runbook:\n"
            + "\n".join(f"- {error}" for error in verification["errors"])
        )
    if status not in DR_CHECKLIST_STATUSES:
        raise CliError(f"Unsupported DR checklist status: {status}")
    if not operator.strip():
        raise CliError("DR checklist updates require --actor")
    if status in DR_COMPLETION_STATUSES and not evidence.strip():
        raise CliError(
            f"DR checklist status {status!r} requires a non-secret --evidence reference"
        )
    if status in {"blocked", "pending"} and not note.strip():
        raise CliError(f"DR checklist status {status!r} requires --note")

    item = resolve_checklist_item(runbook, item_identifier)
    timestamp = clock()
    events = runbook.setdefault("auditTrail", [])
    previous_hash = str(events[-1].get("eventHash") or "") if events else "0" * 64
    event = {
        "sequence": len(events) + 1,
        "timestamp": timestamp,
        "itemId": item["id"],
        "fromStatus": item["status"],
        "toStatus": status,
        "operator": redact_text(operator.strip()),
        "evidence": redact_text(evidence.strip()),
        "note": redact_text(note.strip()),
        "previousHash": previous_hash,
    }
    event["eventHash"] = _event_hash(event)
    events.append(event)
    item.update(
        {
            "status": status,
            "operator": event["operator"],
            "updatedAt": timestamp,
            "completedAt": timestamp if status in DR_COMPLETION_STATUSES else "",
            "evidence": event["evidence"],
            "operatorNote": event["note"],
        }
    )
    runbook["updatedAt"] = timestamp
    _refresh_integrity(runbook)
    return item


def load_disaster_recovery_runbook(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CliError(f"DR runbook not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CliError(f"Invalid JSON in DR runbook {path}: {error}") from error
    if not isinstance(payload, dict):
        raise CliError(f"DR runbook root must be an object: {path}")
    return payload


def save_disaster_recovery_runbook(path: Path, runbook: dict[str, Any]) -> Path:
    """Atomically persist an owner-readable checklist artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(runbook, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


__all__ = [
    "DR_CAPABILITIES",
    "DR_CHECKLIST_STATUSES",
    "DR_COMPLETION_STATUSES",
    "DR_RUNBOOK_KIND",
    "DR_RUNBOOK_SCHEMA_VERSION",
    "KNOWN_EXTERNAL_RECOVERY_AREAS",
    "build_disaster_recovery_runbook",
    "load_disaster_recovery_runbook",
    "resolve_checklist_item",
    "save_disaster_recovery_runbook",
    "summarize_runbook",
    "update_disaster_recovery_checklist",
    "verify_disaster_recovery_runbook",
]
