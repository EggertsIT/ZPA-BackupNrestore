# ZPA API Coverage Audit

Audit date: 2026-07-23

ZPA-Backup and Restore is an independent tool. It is not affiliated with,
endorsed by, sponsored by, certified by, or supported by Zscaler, Inc. It is
provided "as is", without warranty of any kind. See
[DISCLAIMER.md](DISCLAIMER.md).

Primary sources: the current
[Zscaler Automation Hub sitemap](https://automate.zscaler.com/sitemap.xml) and
[ZPA API reference](https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa).

The current sitemap exposes **208 ZPA API reference pages in 44 sections**. The
tool currently declares **136 explicit API operations across 30 modeled
domains**. Those numbers are not a coverage percentage: several SDK-verified
operations do not have an individual sitemap page, and some reference pages
describe aliases or specialized variants of the same endpoint.

Every modeled operation now has its own module under
`zpa_backup_restore/resources/operations/`. Coverage records whether an
operation is:

- `enabled`: used by backup and/or guarded restore;
- `catalog-only`: documented and auditable, but deliberately unavailable to
  generic restore;
- `excluded`: known operation whose output or semantics do not belong in a
  configuration snapshot.

Run `python3 -m zpa_backup_restore coverage` for the live catalog. For JSON that
can be passed directly to another process, disable the run-ledger banner:

```sh
python3 -m zpa_backup_restore --no-run-ledger coverage --json
```

The HTTP audit-log path is written to standard error; the JSON records are
written to standard output.

The sitemap count was produced by selecting URLs beneath the exact
`/docs/api-reference-and-guides/api-reference/zpa/` prefix, counting pages, and
grouping the first path component as a section. The implementation count comes
from the runtime operation registry, not a manual spreadsheet. Re-run both
checks when the official sitemap or operation catalog changes.

## Enabled Clone Coverage

| Domain | Enabled behavior | Important safeguards |
|---|---|---|
| Microtenants | CRUD | All writes require `--allow-high-impact` |
| AppProtection custom controls | CRUD | Predefined controls are not cloned |
| AppProtection profiles | CRUD | Ordered after custom controls |
| CBI banners and profiles | CRUD | CBI banner create uses its singular endpoint |
| App Connector groups | CRUD | Live connector instances excluded |
| Private Service Edge groups | CRUD | Live edge instances excluded |
| Segment groups | CRUD | Name-based cross-tenant identity |
| Application Servers | CRUD | IDs remapped in dependent payloads |
| Server groups | CRUD | Ordered after servers and connector groups |
| Application Segments | CRUD plus move/share | Move/share are separate high-impact operations |
| LSS configurations | CRUD | Receiver reachability remains an operator check |
| PRA portals and consoles | CRUD | Credentials remain excluded |
| Policy rules | CRUD plus bulk reorder | Includes `PRIVILEGED_PORTAL_POLICY`; order restored after changes |

Application Segment move/share planning resolves the destination Microtenant,
Segment Group, Server Group, and Application Segment IDs. New child-Microtenant
applications use a deferred post-create move. Ambiguous, unsupported, or
unresolved operations block simulation; both move and share require
`--allow-high-impact`.

## Reference Inventory And Mapping

| Domain | Coverage |
|---|---|
| Identity Providers | list/detail catalog; list used for backup |
| SAML attributes | global list, IdP-scoped list, and detail catalog; IdP-scoped backup/mapping |
| SCIM attributes and values | list/detail/value catalog; scoped backup/mapping |
| SCIM groups | list/detail catalog; scoped backup/mapping |
| Machine groups | list/detail inventory and mapping |
| Posture profiles | list/detail inventory and mapping |
| Trusted networks | list/detail inventory and mapping |
| Cloud Connector groups | list/detail inventory and mapping |
| Version profiles | list inventory and mapping |
| Zscaler clouds | list inventory; string responses normalized into stable records |
| Enrollment certificates | metadata inventory only; certificate/key fields stripped recursively |
| Browser Access groups | list inventory and mapping |

## Audit-Only And Catalog-Only Coverage

| Domain | Read inventory | Mutations |
|---|---|---|
| Business Continuity settings | Sanitized list/detail | Create/update/delete cataloged but disabled |
| Private Cloud sites | List/detail | CRUD cataloged but disabled pending two-phase association restore |
| Private Cloud Controller groups | List/detail | CRUD cataloged but disabled pending site association restore |
| Live Private Cloud Controllers | List/detail | Update/delete cataloged but disabled |
| Emergency Access users | Cursor-paginated list/detail | Add/update/activate/deactivate cataloged but disabled |
| Privileged Approvals | List/detail | Add/update/delete/expired cleanup cataloged but disabled |

Business Continuity snapshots remove IdP/SP certificate, metadata, and private-key
fields. Generic restore cannot reconstruct those settings safely, so write
operations remain visible but non-executable.

## Explicit Exclusions

The following remain outside generic cloning even when an API exists:

- live App Connector and Private Service Edge instances;
- provisioning keys and nonces;
- privileged credentials and credential moves;
- certificates, certificate bodies, CSRs, and private keys;
- Business Continuity certificate/metadata downloads;
- operational activation, restart, approval-window, and cleanup actions.

## Known Unsupported Or Partial Official Sections

The enabled and reference tables above describe modeled portable
configuration. The following official sitemap sections are intentionally
excluded, catalog-only, audit-only, or only partially represented. “Partial”
means the useful portable operation is modeled; it does not mean every
documentation page in that section maps to an executable operation.

| Official sitemap section(s) | Status | Reason |
|---|---|---|
| `app-connector-management` | Excluded | Live connector instances and cleanup schedules are deployment operations, not portable configuration. |
| `private-service-edge-management` | Excluded | Live service-edge instances are runtime deployments; only service-edge group configuration is cloned. |
| `certificate-management`, `isolation-certificate-management`, `signing-certificate` | Excluded | Certificate bodies, signing material, CSRs, and private keys are sensitive lifecycle data. Enrollment certificates are retained only as stripped metadata. |
| `nonce` | Excluded | Nonces are short-lived bootstrap secrets and cannot be meaningfully restored. |
| `privileged-credential-management` | Excluded | Privileged credentials and credential moves contain or control secrets. PRA portal/console configuration remains separately modeled. |
| `customers`, `delegated-tenant-administration` | Excluded | Customer and delegated-administration lifecycle calls cross the tenant-administration boundary and are too broad for generic configuration restore. |
| `business-continuity-settings` | Catalog-only writes | Sanitized reads are backed up; certificate, metadata, and private-key fields are removed, so generic restore cannot reconstruct the source safely. |
| `site`, `private-cloud-controller-group` | Catalog-only writes | Reads are backed up, but restore requires a deterministic, lab-tested two-phase create/association workflow. |
| `private-cloud-controller` | Audit-only | Controller health and deployment state are operational inventory, not desired portable configuration. |
| `emergency-access-management`, `privileged-approval-management` | Audit-only | Activation, approval windows, and expiry semantics are live security operations rather than ordinary configuration. |
| `application-segment-management`, `appprotection-control-management`, `appprotection-profile-management`, `policy-management`, `siem-config` | Partial by reference page | Core portable CRUD/special operations are modeled. Helper lists, predefined/system objects, aliases, and specialized views are not automatically treated as independent restore actions. |

Provisioning-key operations are also excluded even when they are exposed by an
SDK or a route not represented as an individual page in the current sitemap.
The same rule applies to any newly documented endpoint that returns or mutates
credentials, private keys, bootstrap tokens, or equivalent secrets.

## Current Gaps

The main remaining engineering gap is safe restore—not discovery—for Business
Continuity, Private Cloud/Site, and Controller Group configuration. Their
secret and association requirements need explicit injection contracts plus a
tested two-phase create/update workflow before writes can be enabled.

The coverage audit is deliberately endpoint-aware rather than percentage-based.
New helper, lookup, bulk, or specialized pages must be reviewed individually:
add an operation module and tests when the behavior adds value, or document an
explicit catalog-only/excluded classification when it does not belong in a
portable snapshot.

This project should be described as a guarded ZPA backup, restore, inventory, and
audit tool with explicit partial API coverage. It should not be described as
fully implementing every ZPA API call.
