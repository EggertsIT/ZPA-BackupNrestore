# ZPA API Coverage Audit

Audit date: 2026-06-02

Source used: Zscaler Automation Hub sitemap for ZPA API reference routes:
https://automate.zscaler.com/sitemap.xml

The Automation Hub route set currently exposes 189 ZPA API reference pages across 36 sections. This project is not yet compliant with every documented ZPA function. It implements a focused cloner subset with guarded write behavior and read-only inventory for selected dependencies.

## Implemented Clone Coverage

| Resource | Mode | Notes |
|---|---:|---|
| microtenants | write gated | Requires `--allow-high-impact` for real writes |
| inspection_custom_controls | write | Custom controls only, not predefined controls |
| inspection_profiles | write | Depends on custom controls |
| cbi_banners | read | Inventory only |
| cbi_profiles | write | Cloud Browser Isolation profiles |
| app_connector_groups | write | Groups only, not live connector instances |
| service_edge_groups | write | Groups only, not live service-edge instances |
| segment_groups | write | Full generic CRUD path |
| servers | write | Full generic CRUD path |
| server_groups | write | Depends on servers and app connector groups |
| application_segments | write | Depends on segment/server/service-edge groups and profile resources |
| lss_configs | write | Receiver reachability must be validated manually |
| pra_portals | write | Privileged Remote Access portals |
| pra_consoles | write | Privileged Remote Access consoles |
| machine_groups | read | Inventory only |
| posture_profiles | read | Inventory/reference only |
| trusted_networks | read | Inventory/reference only |
| policy_rules | write | Policy rule CRUD/reorder family partially covered; defaults to `ACCESS_POLICY` |
| idps | read | Identity reference mapping |
| scim_attributes | read | Identity reference mapping |
| scim_groups | read | Identity reference mapping |

## Official ZPA Sections

| Official section | Route count | Current status |
|---|---:|---|
| appprotection-control-management | 17 | Partial: custom controls covered |
| policy-management | 12 | Partial: policy set/rule CRUD covered, helper lists not fully covered |
| log-streaming-service-lss-configuration | 10 | Partial: LSS configs covered, lookup/reference endpoints not all covered |
| appprotection-profile-management | 9 | Partial: inspection profiles covered, special associate/dissociate actions not covered |
| private-service-edge-management | 8 | Not cloned: live instances intentionally excluded |
| isolation-profile-management | 8 | Partial: CBI profile path covered |
| delegated-tenant-administration | 8 | Partial: microtenants covered, scope/session APIs not covered |
| application-segment-management | 8 | Partial: application segment CRUD covered, move/share/special app-type APIs not covered |
| privileged-console-management | 7 | Partial: PRA console CRUD covered, bulk/special portal list endpoint not fully covered |
| certificate-management | 7 | Not cloned: certificate/private key handling is sensitive/manual |
| app-connector-management | 7 | Not cloned: live connector instances intentionally excluded |
| segment-group-management | 6 | Covered for generic CRUD |
| privileged-credential-management | 6 | Not cloned: credentials/secrets excluded |
| privileged-approval-management | 6 | Not covered |
| emergency-access-management | 6 | Not covered |
| server-management | 5 | Covered for generic CRUD |
| server-group-management | 5 | Covered for generic CRUD |
| provisioning-key-management | 5 | Not cloned: provisioning keys/secrets excluded |
| privileged-portal-management | 5 | Partial: PRA portal CRUD covered |
| private-service-edge-group-management | 5 | Covered as service_edge_groups |
| isolation-certificate-management | 5 | Not cloned: certificate/private key handling is sensitive/manual |
| isolation-banner-management | 5 | Read-only inventory only |
| app-connector-group-management | 5 | Covered for generic CRUD |
| scim-attributes | 3 | Read-only reference mapping |
| saml-attributes | 3 | Not covered |
| trusted-networks | 2 | Read-only inventory/reference only |
| scim-groups | 2 | Read-only reference mapping |
| posture-profiles | 2 | Read-only inventory/reference only |
| machine-groups | 2 | Read-only inventory only |
| idp-management | 2 | Read-only reference mapping |
| enrollment-certificates | 2 | Not covered |
| cloud-connector-groups | 2 | Not covered |
| zscaler-private-access-api | 1 | Informational/root page |
| zscaler-clouds | 1 | Not covered |
| version-profiles | 1 | Not covered |
| customers | 1 | Not covered |

## Compliance Position

The current project should be described as:

> A ZPA migration/cloning tool with partial API coverage, focused on application access posture and common dependency objects.

It should not be described as:

> Fully compliant with every ZPA API function documented by Zscaler Automation Hub.

## Next Coverage Targets

Reasonable next targets:

1. Add read-only reference mapping for SAML attributes, version profiles, zscaler clouds, enrollment certificates, and cloud connector groups.
2. Add special operations for application segment move/share and policy rule reorder.
3. Add admin/report-only inventory for emergency access and privileged approvals.
4. Keep certificates, provisioning keys, privileged credentials, live connectors, and live service edges out of generic cloning unless explicit secret-handling workflows are designed.
