# Changelog

Notable user-visible changes are recorded here. This project uses semantic
versioning for application releases; persisted artifact schemas are versioned
separately.

## Unreleased

- Reconciled coverage, safety, simulation, and architecture terminology across
  the README, specification, task ledger, and operator documentation.
- Added contribution, pull-request, lab-rehearsal, unsupported-API, versioning,
  and release guidance.
- Declared the source-distribution documentation set and prevented cached
  bytecode from being treated as wheel package data.
- Replaced the desktop UI’s vertically scrolling control stack with focused
  Workflow, Tenants, Options, Scope, Artifacts, and Status tabs that fit at the
  minimum supported window size.
- Added first-class selective restore for individual stable resource identities
  or complete writable resource types, with explicit dependency expansion and
  opt-in policy reorder.
- Bound selective scope into preflight recomputation, simulation assurance,
  fresh-target drift checks, execution journals, run-ledger events, reports,
  and scoped residual verification.
- Added canonical selectors and copyable restore-plan commands to inventory
  output, plus matching desktop Scope controls.
- Added contextual desktop tooltips for navigation tabs, workflow actions,
  tenant fields, artifacts, selective scope, and restore safeguards. Tooltips
  work with pointer hover and keyboard focus without changing the compact
  non-scrolling layout.

## 2.0.0 - 2026-07-23

- Reorganized the maintained implementation into the
  `zpa_backup_restore` package while preserving legacy entry points and backup
  schema `1.0`.
- Added declarative per-operation API coverage grouped into domain packages.
- Added offline restore simulation, reviewed-plan assurance, fresh-destination
  drift protection, execution journals, and post-restore residual verification.
- Added a managed SQLite snapshot catalog, credential-free inventory and drift
  queries, and a tamper-evident run ledger.
- Expanded guarded clone, reference inventory, sanitized catalog-only, and
  audit-only ZPA coverage as recorded in
  [ZPA_API_COVERAGE_AUDIT.md](ZPA_API_COVERAGE_AUDIT.md).
