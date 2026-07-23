"""Ordered registry assembled from resource-owned modules."""

from __future__ import annotations

from . import (
    app_connector_groups,
    application_segments,
    cbi,
    inspection_controls,
    inspection_profiles,
    lss_configs,
    microtenants,
    operational_inventory,
    platform_references,
    pra,
    protected_configuration,
    reference_inventory,
    segment_groups,
    server_groups,
    servers,
    service_edge_groups,
)
from .identity_references import READ_ONLY_REFERENCE_RESOURCES as _REFERENCE_RESOURCES
from .model import ResourceSpec
from .operations.identity import OPERATIONS as _IDENTITY_OPERATIONS
from .operations.policy import OPERATIONS as _POLICY_OPERATIONS
from .policy_rules import POLICY_TYPES as _POLICY_TYPES


_ORDERED_SPECS: tuple[ResourceSpec, ...] = (
    microtenants.SPEC,
    inspection_controls.SPEC,
    inspection_profiles.SPEC,
    cbi.BANNERS,
    cbi.PROFILES,
    app_connector_groups.SPEC,
    service_edge_groups.SPEC,
    segment_groups.SPEC,
    servers.SPEC,
    server_groups.SPEC,
    application_segments.SPEC,
    lss_configs.SPEC,
    pra.PORTALS,
    pra.CONSOLES,
    *reference_inventory.SPECS,
    *platform_references.SPECS,
    *protected_configuration.SPECS,
    *operational_inventory.SPECS,
)

RESOURCE_SPECS = {spec.key: spec for spec in _ORDERED_SPECS}
RESOURCES = {key: spec.as_legacy_dict() for key, spec in RESOURCE_SPECS.items()}


def _special_coverage(
    *,
    path: str,
    mode: str,
    sensitivity: str,
    operations: tuple,
    notes: str,
) -> dict:
    return {
        "path": path,
        "detail_path": None,
        "detail_strategy": "special",
        "id_field": "id",
        "name_field": "name",
        "writable": any(
            operation.mutating and operation.support == "enabled"
            for operation in operations
        ),
        "depends_on": [],
        "skip_fields": set(),
        "notes": notes,
        "high_impact": any(operation.high_impact for operation in operations),
        "mode": mode,
        "sensitivity": sensitivity,
        "actions": [operation.key for operation in operations],
        "enabled_actions": [
            operation.key for operation in operations if operation.support == "enabled"
        ],
        "operations": [operation.as_dict() for operation in operations],
        "optional": False,
        "backup_skip_fields": set(),
        "pagination": "special",
        "operation_source": "explicit",
    }


COVERAGE_RESOURCES = {
    **RESOURCES,
    "identity_references": _special_coverage(
        path="/mgmtconfig/v2/admin/customers/{customer_id}/idp",
        mode="reference",
        sensitivity="sensitive",
        operations=_IDENTITY_OPERATIONS,
        notes="IdP, SAML, and SCIM inventory used for scoped cross-tenant ID mapping.",
    ),
    "policy_rules": _special_coverage(
        path="/mgmtconfig/v1/admin/customers/{customer_id}/policySet",
        mode="clone",
        sensitivity="high-impact",
        operations=_POLICY_OPERATIONS,
        notes="Policy CRUD plus individual and deterministic bulk reorder operations.",
    ),
}
POLICY_TYPES = list(_POLICY_TYPES)
READ_ONLY_REFERENCE_RESOURCES = list(_REFERENCE_RESOURCES)

MIGRATION_ORDER = [
    "microtenants",
    "inspection_custom_controls",
    "inspection_profiles",
    "cbi_banners",
    "cbi_profiles",
    "app_connector_groups",
    "service_edge_groups",
    "segment_groups",
    "servers",
    "server_groups",
    "application_segments",
    "lss_configs",
    "pra_portals",
    "pra_consoles",
    "policy_rules",
]


def migration_order_issues(order: list[str] | None = None) -> list[str]:
    """Return dependency-order violations in a proposed restore order."""
    order = order or MIGRATION_ORDER
    positions = {key: index for index, key in enumerate(order)}
    issues = []
    for key in order:
        if key == "policy_rules":
            continue
        spec = RESOURCE_SPECS.get(key)
        if not spec:
            issues.append(f"{key} is in MIGRATION_ORDER but not RESOURCES")
            continue
        for dependency in spec.depends_on:
            if dependency not in positions:
                issues.append(f"{key} depends on {dependency}, but {dependency} is not in MIGRATION_ORDER")
            elif positions[dependency] > positions[key]:
                issues.append(f"{key} appears before dependency {dependency} in MIGRATION_ORDER")
    return issues
