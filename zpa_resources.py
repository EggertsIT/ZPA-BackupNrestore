"""ZPA resource catalog for the tenant cloner.

The catalog intentionally starts with the resources most commonly required to
move access posture between ZPA tenants. The operation names and URL families
match the official Zscaler Automation Hub ZPA API reference and the local
OneAPI Postman collection in this workspace.
"""

from __future__ import annotations


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


def resource(
    path: str,
    *,
    detail_path: str | None = None,
    detail_strategy: str = "detail",
    id_field: str = "id",
    name_field: str = "name",
    writable: bool = True,
    depends_on: list[str] | None = None,
    skip_fields: set[str] | None = None,
    notes: str = "",
    high_impact: bool = False,
) -> dict:
    return {
        "path": path,
        "detail_path": detail_path,
        "detail_strategy": detail_strategy,
        "id_field": id_field,
        "name_field": name_field,
        "writable": writable,
        "depends_on": depends_on or [],
        "skip_fields": set(skip_fields or set()),
        "notes": notes,
        "high_impact": high_impact,
    }


RESOURCES: dict[str, dict] = {
    "microtenants": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/microtenants",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/microtenants/{id}",
        notes="High-impact tenant partitioning object. Review carefully before applying across tenants.",
        high_impact=True,
    ),
    "inspection_custom_controls": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom/{id}",
        notes="Custom inspection controls. Predefined controls are not cloned.",
    ),
    "inspection_profiles": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile/{id}",
        depends_on=["inspection_custom_controls"],
    ),
    "cbi_banners": resource(
        "/cbiconfig/cbi/api/customers/{customer_id}/banners",
        detail_path="/cbiconfig/cbi/api/customers/{customer_id}/banners/{id}",
        writable=False,
        notes="Browser Isolation banner inventory. Add endpoint was not present in the local collection; kept read-only.",
    ),
    "cbi_profiles": resource(
        "/cbiconfig/cbi/api/customers/{customer_id}/profiles",
        detail_path="/cbiconfig/cbi/api/customers/{customer_id}/profiles/{id}",
        notes="Cloud Browser Isolation profiles.",
    ),
    "app_connector_groups": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup/{id}",
        skip_fields={"connectors", "appConnectors"},
        notes="App Connector instances themselves are not cloned; only group configuration is handled.",
    ),
    "service_edge_groups": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup/{id}",
        skip_fields={"serviceEdges"},
        notes="Private Service Edge instances are not cloned; only group configuration is handled.",
    ),
    "segment_groups": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup/{id}",
    ),
    "servers": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/server",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/server/{id}",
    ),
    "server_groups": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup/{id}",
        depends_on=["servers", "app_connector_groups"],
    ),
    "application_segments": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/application",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}",
        detail_strategy="list",
        depends_on=["segment_groups", "server_groups", "service_edge_groups", "inspection_profiles", "cbi_profiles"],
        notes="The application list endpoint returns detailed records and is used directly to avoid per-segment reads.",
    ),
    "lss_configs": resource(
        "/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig",
        detail_path="/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig/{id}",
        depends_on=["app_connector_groups", "service_edge_groups"],
        notes="Log Streaming Service configurations. Receiver/network reachability must be validated manually.",
    ),
    "pra_portals": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/praPortal",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/praPortal/{id}",
        depends_on=["application_segments"],
    ),
    "pra_consoles": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/praConsole",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/praConsole/{id}",
        depends_on=["pra_portals", "server_groups", "application_segments"],
    ),
    "machine_groups": resource(
        "/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup/{id}",
        writable=False,
        notes="Machine group inventory. No create/update/delete endpoints were present in the local collection.",
    ),
    "posture_profiles": resource(
        "/mgmtconfig/v2/admin/customers/{customer_id}/posture",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/posture/{id}",
        writable=False,
        notes="Posture profile inventory. Policy rules can reference these IDs; target posture must already exist.",
    ),
    "trusted_networks": resource(
        "/mgmtconfig/v2/admin/customers/{customer_id}/network",
        detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/network/{id}",
        writable=False,
        notes="Trusted network inventory. Policy rules can reference these IDs; target trusted networks must already exist.",
    ),
}


POLICY_TYPES = [
    "ACCESS_POLICY",
    "TIMEOUT_POLICY",
    "CLIENT_FORWARDING_POLICY",
    "INSPECTION_POLICY",
    "ISOLATION_POLICY",
    "CREDENTIAL_POLICY",
    "CAPABILITIES_POLICY",
    "CLIENTLESS_SESSION_PROTECTION_POLICY",
    "REDIRECTION_POLICY",
]


MIGRATION_ORDER = [
    "microtenants",
    "inspection_custom_controls",
    "inspection_profiles",
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


READ_ONLY_REFERENCE_RESOURCES = [
    "idps",
    "scim_attributes",
    "scim_groups",
]


def migration_order_issues(order: list[str] | None = None) -> list[str]:
    order = order or MIGRATION_ORDER
    positions = {key: index for index, key in enumerate(order)}
    issues = []
    for key in order:
        if key == "policy_rules":
            continue
        meta = RESOURCES.get(key)
        if not meta:
            issues.append(f"{key} is in MIGRATION_ORDER but not RESOURCES")
            continue
        for dependency in meta.get("depends_on", []):
            if dependency not in positions:
                issues.append(f"{key} depends on {dependency}, but {dependency} is not in MIGRATION_ORDER")
            elif positions[dependency] > positions[key]:
                issues.append(f"{key} appears before dependency {dependency} in MIGRATION_ORDER")
    return issues
