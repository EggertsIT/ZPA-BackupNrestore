"""Compatibility import for the resource-owned v2 registry."""

from zpa_backup_restore.resources.registry import (
    COVERAGE_RESOURCES,
    MIGRATION_ORDER,
    POLICY_TYPES,
    READ_ONLY_REFERENCE_RESOURCES,
    RESOURCES,
    RESOURCE_SPECS,
    migration_order_issues,
)

SYSTEM_FIELDS = {
    "id",
    "creationTime",
    "modifiedTime",
    "modifiedBy",
    "lastModifiedTime",
    "lastModifiedBy",
    "modifiedByName",
    "ownerId",
    "version",
    "ziaCloud",
}

WRITE_SKIP_FIELDS = {
    "connectors",
    "appConnectors",
    "serviceEdges",
    "connectorCount",
    "serverCount",
    "applicationCount",
    "applications",
    "readOnly",
}


def resource(path: str, **options: object) -> dict:
    """Legacy helper retained for downstream imports."""
    return {
        "path": path,
        "detail_path": options.get("detail_path"),
        "detail_strategy": options.get("detail_strategy", "detail"),
        "id_field": options.get("id_field", "id"),
        "name_field": options.get("name_field", "name"),
        "writable": options.get("writable", True),
        "depends_on": options.get("depends_on") or [],
        "skip_fields": set(options.get("skip_fields") or set()),
        "notes": options.get("notes", ""),
        "high_impact": options.get("high_impact", False),
    }


__all__ = [
    "COVERAGE_RESOURCES",
    "MIGRATION_ORDER",
    "POLICY_TYPES",
    "READ_ONLY_REFERENCE_RESOURCES",
    "RESOURCES",
    "RESOURCE_SPECS",
    "SYSTEM_FIELDS",
    "WRITE_SKIP_FIELDS",
    "migration_order_issues",
    "resource",
]
