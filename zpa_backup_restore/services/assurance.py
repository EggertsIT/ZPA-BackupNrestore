"""Deterministic simulation binding and destination-drift protection."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from zpa_backup_restore.core.integrity import canonical_json
from zpa_backup_restore.core.selection import (
    compute_restore_diff,
    scope_from_diff,
    scope_inventory_keys,
)
from zpa_backup_restore.core.simulation import simulate_restore
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.services.snapshots import build_inventory


SIMULATION_ASSURANCE_SCHEMA_VERSION = "1.0"


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalized_state_sha256(
    backup: dict[str, Any],
    scope: dict[str, Any] | None = None,
) -> str:
    """Hash stable identities/configurations, excluding timestamps and tenant object IDs."""
    resources, _references = build_inventory("normalized-state", backup)
    whole_types, selected_keys = scope_inventory_keys(scope)
    if scope is not None:
        resources = [
            resource
            for resource in resources
            if resource.resource_type in whole_types
            or resource.stable_key in selected_keys.get(resource.resource_type, set())
        ]
    state = [
        {
            "resourceType": resource.resource_type,
            "stableKey": resource.stable_key,
            "configSha256": resource.config_sha256,
        }
        for resource in sorted(resources, key=lambda item: (item.resource_type, item.stable_key))
    ]
    return document_sha256(state)


def _plan_material(simulation: dict[str, Any]) -> dict[str, Any]:
    """Select all execution-significant, deterministic fields from a simulation."""
    return {
        "kind": simulation.get("kind"),
        "schemaVersion": simulation.get("schemaVersion"),
        "scope": simulation.get("scope"),
        "sourceCustomerId": simulation.get("sourceCustomerId"),
        "targetCustomerId": simulation.get("targetCustomerId"),
        "safeguards": simulation.get("safeguards"),
        "summary": simulation.get("summary"),
        "skipReasons": simulation.get("skipReasons"),
        "hasBlockingIssues": simulation.get("hasBlockingIssues"),
        "operations": simulation.get("operations"),
    }


def plan_sha256(simulation: dict[str, Any]) -> str:
    return document_sha256(_plan_material(simulation))


def attach_simulation_assurance(
    simulation: dict[str, Any],
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    diff: dict[str, Any],
) -> dict[str, Any]:
    secured = json.loads(json.dumps(simulation))
    scope = scope_from_diff(diff)
    secured["assurance"] = {
        "schemaVersion": SIMULATION_ASSURANCE_SCHEMA_VERSION,
        "sourceBackupSha256": document_sha256(source_backup),
        "targetBackupSha256": document_sha256(target_backup),
        "diffSha256": document_sha256(diff),
        "targetStateSha256": normalized_state_sha256(target_backup, scope),
        "planSha256": plan_sha256(secured),
    }
    return secured


def build_assured_simulation(
    diff: dict[str, Any],
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    *,
    allow_delete: bool,
    allow_high_impact: bool,
) -> dict[str, Any]:
    simulation = simulate_restore(
        diff,
        source_backup,
        target_backup,
        allow_delete=allow_delete,
        allow_high_impact=allow_high_impact,
    )
    return attach_simulation_assurance(simulation, source_backup, target_backup, diff)


def validate_reviewed_simulation(
    reviewed: dict[str, Any],
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    diff: dict[str, Any],
    *,
    allow_delete: bool,
    allow_high_impact: bool,
) -> None:
    issues: list[str] = []
    assurance = reviewed.get("assurance")
    if reviewed.get("kind") != "restore-simulation":
        issues.append("artifact is not a restore simulation")
    if not isinstance(assurance, dict):
        issues.append("simulation assurance metadata is missing")
        assurance = {}
    if assurance.get("schemaVersion") != SIMULATION_ASSURANCE_SCHEMA_VERSION:
        issues.append("simulation assurance schema is unsupported")

    scope = scope_from_diff(diff)
    expected_hashes = {
        "sourceBackupSha256": document_sha256(source_backup),
        "targetBackupSha256": document_sha256(target_backup),
        "diffSha256": document_sha256(diff),
        "targetStateSha256": normalized_state_sha256(target_backup, scope),
    }
    for key, expected in expected_hashes.items():
        if not hmac.compare_digest(str(assurance.get(key, "")), expected):
            issues.append(f"simulation {key} does not match the selected restore input")

    supplied_plan_hash = str(assurance.get("planSha256", ""))
    if not hmac.compare_digest(supplied_plan_hash, plan_sha256(reviewed)):
        issues.append("simulation plan SHA-256 is invalid")

    safeguards = reviewed.get("safeguards", {})
    if safeguards.get("allowDelete") is not allow_delete:
        issues.append("simulation delete safeguard does not match this restore")
    if safeguards.get("allowHighImpact") is not allow_high_impact:
        issues.append("simulation high-impact safeguard does not match this restore")
    if reviewed.get("hasBlockingIssues") or reviewed.get("summary", {}).get("blocked"):
        issues.append("simulation contains blocking operations")

    expected = build_assured_simulation(
        diff,
        source_backup,
        target_backup,
        allow_delete=allow_delete,
        allow_high_impact=allow_high_impact,
    )
    if not hmac.compare_digest(supplied_plan_hash, expected["assurance"]["planSha256"]):
        issues.append("reviewed plan does not match a fresh simulation of the selected inputs")
    if issues:
        raise CliError(
            "Reviewed simulation validation failed:\n" + "\n".join(f"- {issue}" for issue in issues)
        )


def fresh_destination_diff(
    reviewed: dict[str, Any],
    source_backup: dict[str, Any],
    fresh_target_backup: dict[str, Any],
    *,
    allow_delete: bool,
    allow_high_impact: bool,
) -> dict[str, Any]:
    """Return a fresh diff only when destination state and exact ordered plan remain unchanged."""
    assurance = reviewed.get("assurance", {})
    reviewed_scope = reviewed.get("scope")
    if reviewed_scope is not None and not isinstance(reviewed_scope, dict):
        raise CliError("Reviewed simulation scope must be an object")
    fresh_state_hash = normalized_state_sha256(fresh_target_backup, reviewed_scope)
    if not hmac.compare_digest(str(assurance.get("targetStateSha256", "")), fresh_state_hash):
        raise CliError(
            "Destination drift detected: the target changed after the reviewed simulation. "
            "Create and review a new restore plan."
        )
    diff = compute_restore_diff(
        source_backup,
        fresh_target_backup,
        scope=reviewed_scope,
    )
    fresh_simulation = build_assured_simulation(
        diff,
        source_backup,
        fresh_target_backup,
        allow_delete=allow_delete,
        allow_high_impact=allow_high_impact,
    )
    if not hmac.compare_digest(
        str(assurance.get("planSha256", "")),
        fresh_simulation["assurance"]["planSha256"],
    ):
        raise CliError(
            "Destination drift detected: the fresh target would produce a different ordered plan. "
            "Create and review a new restore plan."
        )
    return diff


__all__ = [
    "SIMULATION_ASSURANCE_SCHEMA_VERSION",
    "attach_simulation_assurance",
    "build_assured_simulation",
    "document_sha256",
    "fresh_destination_diff",
    "normalized_state_sha256",
    "plan_sha256",
    "validate_reviewed_simulation",
]
