# Progress

This file records completed work, verification, skipped checks, and known risks. Update it after each task from `TASKS.md`.

## 2026-07-23

### Disaster Recovery Runbook

- Added a credential-free DR service that builds a versioned canonical JSON
  runbook and printable HTML checklist from plain or encrypted backups.
- Enumerated every captured setting, all 30 modeled domains and 136 explicit
  operations, endpoint failures, optional/missing domains, and six known
  external recovery areas.
- Classified every item as guarded automated restore, Destination reference,
  protected manual recovery, operational audit validation, or external
  recovery. Automated commands are generated only for stable writable objects.
- Added readiness, infrastructure, change-control, per-domain, per-setting,
  external recovery, residual-diff, reference/order, business-service,
  ledger/evidence, and closure procedures.
- Added evidence-required `dr check` updates with actor, timestamp, prior/new
  status, notes, atomic persistence, deterministic plan/state hashes, and a
  hash-chained checklist event trail.
- Added credential-free `dr generate`, `status`, `check`, `report`, and
  `verify` commands with run-ledger input/output artifact hashes.
- Added a compact `DR Runbook` desktop action, JSON/HTML artifact capture,
  contextual guidance, and direct `Open DR Checklist` access.
- The UI/UX Utility Clean direction keeps the action in the existing Review
  row and adds no Workflow-tab height.

### Disaster Recovery Runbook Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest discover -q` with 100 tests.
- Passed focused runbook coverage, incomplete-backup, evidence, hash-chain,
  tamper-detection, printable-report, CLI, encrypted-backup, and UI tests.
- Passed CLI help checks for `dr generate`, `status`, `check`, `report`, and
  `verify`.
- Rechecked all six tabs at the 1040×700 minimum window. The notebook had
  593 px available; requested heights were Workflow 546, Tenants 350, Options
  460, Scope 521, Artifacts 436, and Status 258, with no overflow.
- Rebuilt `dist/ZPA-Backup and Restore.app` and verified that the current DR
  service and reporting modules are included.
- Passed `plutil -lint` for the generated `Info.plist`.
- Passed `sh -n` for the generated macOS launcher.
- Passed: `git diff --check`.
- Type checking remains skipped because no static type checker is configured.
- No live tenant calls were made.

### Contextual UI Tooltips

- Added a reusable delayed tooltip component that supports pointer hover and
  keyboard focus without changing the compact tab layout.
- Added plain-language explanations for all six navigation tabs, every workflow
  action, tenant API fields, backup encryption, artifact paths, selective
  restore controls, and restore safeguards.
- Made safety impact explicit for Destination writes, credential copying,
  deletes, high-impact actions, incomplete backups, and preflight bypass.
- Kept every core action operable from its visible label; tooltips are
  supplementary guidance rather than a required interaction.

### Contextual UI Tooltip Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest discover -v` with 92 tests.
- Passed focused coverage checks for all tabs, workflow actions, tenant fields,
  artifacts, and safeguards.
- Passed live Tk pointer-hover and keyboard-focus rendering checks. The UI has
  118 contextual tooltip targets.
- Rechecked the 1040×700 minimum window: 593 px were available to the active
  left tab and the largest requested tab height remained 546 px.
- Rebuilt `dist/ZPA-Backup and Restore.app` and verified that the tooltip code
  is included in the bundle.
- Passed `plutil -lint` for the generated `Info.plist`.
- Passed `sh -n` for the generated macOS launcher.
- Passed: `git diff --check`.
- Type checking remains skipped because no static type checker is configured.
- No live tenant calls were made.

### Selective Restore

- Added stable individual selectors and whole-domain selectors at diff creation:
  ordinary resources use `RESOURCE_TYPE/normalized-name`; policy rules use
  `policy_rules/POLICY_TYPE:normalized-name`.
- Added explicit recursive dependency inclusion and kept policy bulk reorder
  opt-in for selective policy recovery.
- Persisted resolved scope in diffs and reports. Preflight recomputes scoped
  changes so hand-edited omissions are rejected.
- Bound scope into simulation hashes, normalized destination state, fresh-plan
  drift checks, execution, run-ledger events, and post-restore residual
  verification. Unrelated tenant drift is ignored for targeted recovery.
- Added inventory restore selectors and copyable `restore-plan` commands.
  `restore-plan` now prints the next simulation command, and simulation prints
  the exact reviewed restore command.
- Added a desktop `Scope` tab for canonical object selectors, complete writable
  resource types, explicit dependencies, and policy-order restoration.
- The UI/UX Utility Clean direction kept restore controls in a dedicated,
  non-scrolling tab rather than mixing scope with credentials or workflow
  actions.

### Selective Restore Checks

- Passed: `python3 -m unittest -v` with 91 tests.
- Passed focused selector, whole-domain, ambiguity, dependency, policy-order,
  scoped-preflight, scoped-drift, live-executor, inventory-command, and UI
  argument tests.
- Passed: `python3 -m py_compile` for changed Python modules and tests.
- Measured all six UI tabs at the 1040×700 minimum. Available content height is
  555 px; requested heights are Workflow 546, Tenants 350, Options 460, Scope
  521, Artifacts 352, and Status 258.
- Type checking remains skipped because no static type checker is configured.
- No live tenant calls were made; live ZPA validation remains required before a
  production release.

### Compact Non-Scrolling Desktop Layout

- Replaced the left-side canvas and vertical scrollbar with focused tabs:
  Workflow, Tenants, Options, Scope, Artifacts, and Status.
- Kept ordered operational actions together in Workflow while separating
  credential entry, policy/safety choices, files, and readiness information.
- Compacted credential fields, policy types, and restore safeguards into
  accessible two-column grids with shorter human-readable policy labels.
- Measured every tab at the minimum 1040×700 window size. The current
  measurements are recorded in Selective Restore Checks above.
- Updated the specification, task ledger, README, process documentation, and
  UI helper tests.

### Compact UI Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest discover -v` with 91 tests.
- Passed focused tab-model, compact-grid, invalid-coordinate, and policy-label
  tests.
- Passed live Tk layout measurement at the 1040×700 minimum window size with no
  overflowing left-side tab.
- Rebuilt `dist/ZPA-Backup and Restore.app`.
- Passed `plutil -lint` for the generated `Info.plist`.
- Passed `sh -n` for the generated macOS launcher.
- Passed: `git diff --check`.
- Type checking remains skipped because no static type checker is configured.

### Documentation And Release Readiness

- Reconciled the README, specification, architecture, tasks, and coverage audit
  with the implemented hybrid domain/per-operation architecture.
- Corrected CBI banners from read-only to guarded CRUD, made `simulate` the
  canonical workflow term, and documented every current clone, reference,
  catalog-only, audit-only, and excluded resource category.
- Revalidated the official Automation Hub sitemap at 208 ZPA reference pages
  across 44 sections and documented the counting method, unsupported API
  families, partial sections, and safety rationale.
- Added a lab-tenant production rehearsal and recovery exercise, contribution
  and branch strategy, pull-request checklist, changelog, version-bump process,
  and Python/macOS release checklist.
- Clarified that unchecked task boxes are explicit future backlog rather than
  claims about implemented behavior.
- Added an explicit source-distribution documentation manifest and disabled
  implicit package data so cached bytecode cannot enter a clean wheel.

### Documentation And Packaging Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest discover -v` with 72 tests.
- Passed machine-readable coverage validation: 30 domains, 136 operations, zero
  compatibility/inferred entries.
- Passed CLI help checks for snapshot, inventory, audit, simulate, and restore.
- Passed local Markdown link, anchor, code-fence, and duplicate-heading audit;
  repeated historical subheadings in this progress log are intentional.
- Passed official sitemap recount: 208 ZPA pages across 44 sections.
- Passed clean-source wheel validation with all operation and compatibility
  modules and zero cached bytecode files.
- Passed clean-source archive validation with all eight required operator and
  project documentation files and zero cached bytecode files.
- Passed: `git diff --check`.
- `python3 -m build` was skipped because the optional development-only `build`
  package is not installed; clean wheel and source archives were validated
  through the available setuptools/pip build backends.
- Type checking remains skipped because no static type checker is configured.
- No live tenant calls were made during this documentation pass.

### Explicit API Operation Architecture And Coverage

- Added immutable `OperationSpec` declarations and grouped operation packages:
  every modeled HTTP action now has its own auditable module, while domain
  modules compose operations with identity, dependency, payload, and safety
  behavior.
- Converted all modeled resources away from inferred CRUD. The coverage command
  now reports 30 domains and 136 explicit operation declarations, including
  `enabled`, `catalog-only`, and `excluded` support status.
- Refreshed the official Automation Hub sitemap audit to 208 ZPA reference pages
  across 44 sections.
- Added SAML, version profile, Zscaler cloud, enrollment-certificate metadata,
  Cloud Connector group, and Browser Access group inventory and cross-tenant
  mapping. Enrollment certificate fields are recursively stripped.
- Added `PRIVILEGED_PORTAL_POLICY` and deterministic bulk rule reordering after
  creates, updates, and deletes.
- Added guarded Application Segment move/share planning and execution, including
  deferred moves for newly created child-Microtenant applications.
- Added cursor pagination plus audit-only Private Cloud Controller, Emergency
  Access user, and Privileged Approval inventory. Their operational mutations
  are cataloged but cannot be invoked by generic restore.
- Added sanitized Business Continuity and Private Cloud/Site/Controller Group
  inventory. Secret-bearing and two-phase association writes remain
  `catalog-only`.
- Kept historical schema-1.0 snapshots valid when newer optional resources are
  absent.

### Known Safety Boundary

- Business Continuity restore remains disabled because snapshots intentionally
  exclude certificate/private-key material.
- Private Cloud/Site and Controller Group restore remains disabled until a
  deterministic two-phase association workflow is implemented and lab-tested.
- No live tenant calls were made; endpoint behavior is covered with unit fakes
  and declarations verified against current official documentation and SDKs.

### Coverage Expansion Checks

- Passed: `python3 -m compileall -q .`.
- Passed: `python3 -m unittest discover -v` with 72 tests.
- Passed focused endpoint, pagination, secret-stripping, SAML mapping, policy
  reorder, Application Segment move/share, coverage JSON, and historical
  snapshot compatibility tests.
- Passed machine-readable coverage validation: 30 domains, 136 operations, zero
  compatibility/inferred entries.
- Passed: `python3 -m zpa_backup_restore --help`.
- Passed wheel build for `zpa_backup_restore-2.0.0`; operation packages and
  protected configuration modules are included.
- Passed: `git diff --check`.
- Type checking remains skipped because no static type checker is configured.

## 2026-07-19

### Managed Recovery Platform

- Added immutable domain records, repository protocols, application services, and thin CLI/UI adapters for managed snapshots, inventory, auditing, and restore assurance.
- Added a versioned owner-only SQLite catalog at `state/catalog.sqlite3`; backup payloads and credentials are not stored in it.
- Automatically cataloged backups created by backup, plan, restore-plan, and restore checkpoint workflows.
- Added credential-free snapshot import/list/show/verify and inventory list/search/history/references/drift commands with JSON/CSV export.
- Added generic resource-reference indexing, stable configuration hashes, content-derived snapshot IDs, tenant fingerprints, and artifact verification.
- Added a UUID-correlated, secret-redacted run ledger with a SHA-256 event chain and separate head checkpoint, plus list/show/summary/failures/verify commands.
- Added deterministic simulation hashes for the source backup, reviewed target, diff, normalized target state, safeguards, and exact ordered operation plan.
- Made reviewed simulation JSON mandatory for live restore by default; the compatibility bypass is explicit and recorded in the run ledger.
- Added a fresh pre-write destination snapshot and state/exact-plan drift gate.
- Added an atomically persisted per-operation execution journal, post-restore destination snapshot, residual diff, and verification report. Residual changes return failure.
- Updated the desktop workflow with a dedicated reviewed-simulation artifact and credential-free Snapshot, Inventory, Audit Summary, and Verify Ledger actions.
- Added `docs/OPERATIONS.md` for security, retention, ledger limitations, recovery, and managed CLI operation.
- Chose safe interruption recovery by capturing current destination state and building a new reviewed plan; the tool does not blindly replay a partially completed journal.

### Managed Recovery Checks

- Passed: `python3 -m compileall -q .`.
- Passed: `python3 -m unittest discover -v` with 64 tests.
- Passed focused SQLite migration, restrictive-permission, no-payload/no-secret, reference, history, drift, and credential-free CLI tests.
- Passed focused ledger redaction, chain modification, event removal, tail truncation, query, permission, and credential-free verification tests.
- Passed focused assurance input/safeguard/plan tamper, configuration drift, object-ID drift, and credential-before-write gate tests.
- Passed atomic execution-journal and created-destination-ID tests.
- Passed canonical `snapshot`, `inventory`, and `audit` help entry points.
- Passed wheel build and verified the catalog, ledger, inventory, and assurance modules are packaged.
- Passed: `python3 build_macos_app.py`; the bundle contains managed-recovery services and `docs/OPERATIONS.md`.
- Passed: `plutil -lint`, launcher `sh -n`, bundle version `2.0.0`, and `git diff --check`.
- No live tenant calls were made; tenant reads/writes remain represented by unit fakes.
- Type checking: skipped because no static type checker is configured yet.

### Restore Simulation Upgrade

- Replaced the limited dry-run path with a deterministic offline restore simulator.
- Added the canonical `simulate` command; `restore --dry-run` and `apply --dry-run` dispatch to the same implementation for compatibility.
- Removed the tenant-credential requirement from simulation in both CLI behavior and the desktop UI.
- Added ordered operation records containing action, resource, dependencies, source/target IDs, HTTP method, destination path, sanitized request body, payload completeness, and safety status.
- Added symbolic `$planned:<resource>:<source-id>` references for IDs that will be returned by earlier creates.
- Added blocking field-path diagnostics for unmapped source IDs, missing target object IDs, and missing target policy sets.
- Added exact delete/high-impact safety parity and skip counts grouped by reason.
- Added dedicated simulation JSON and HTML artifacts with planned, skipped, blocked, deferred, and unresolved summaries.
- Added a live-restore simulation gate that refuses to load destination credentials when blocking payload issues exist.
- Centralized persisted-artifact redaction for HTML reports and simulation payloads.
- Renamed the desktop workflow action from `Dry Run` to `Simulate` and taught it to capture simulation artifacts.

### Restore Simulation Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest -v` with 54 tests.
- Passed: canonical and compatibility `simulate --help` entry points.
- Passed: credential-free CLI simulation test with JSON and HTML output.
- Passed: live restore blocks unresolved references before loading tenant credentials.
- Passed: deferred-ID ordering, safeguard grouping, missing-target-ID, field-path diagnostic, payload-redaction, UI artifact, and report tests.
- Passed: `python3 build_macos_app.py` and bundled simulator presence check.
- Passed: wheel build and verified `core/simulation.py`, `security.py`, and the console entry point are packaged.
- Passed: `plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"`.
- Passed: `sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"`.
- Passed: `git diff --check`.
- Type checking: skipped because no static type checker is configured yet.

### Completed

- Released the maintainability foundation for version `2.0.0`:
  - Added the versioned `zpa_backup_restore` package and canonical `python3 -m zpa_backup_restore` CLI.
  - Added package metadata and the installed `zpa-backup-restore` console command.
  - Split resource API definitions into one module per resource or closely related domain.
  - Added a typed `ResourceSpec` contract and ordered registry with safety-derived supported actions.
  - Separated backup/pagination, diffing, ID mapping, guarded restore, integrity, encrypted storage, reporting, CLI, API adapter, and error concerns.
  - Converted the main cloner, resource catalog, integrity, and report top-level modules into compatibility façades.
  - Kept the backup manifest schema at `1.0` so valid existing backups remain readable.
  - Aligned the Python package and macOS bundle at version `2.0.0` and included the package in the app bundle.
  - Added `docs/ARCHITECTURE.md` with the design rationale and API-extension workflow.
  - Added five v2 architecture and compatibility tests.

### Checks

- Passed: `python3 -m compileall -q zpa_backup_restore *.py`.
- Passed: `python3 -m unittest -v` with 46 tests.
- Passed: `python3 -m zpa_backup_restore --help`.
- Passed: `python3 -m zpa_backup_restore coverage --json`.
- Passed: wheel build with `python3 -m pip wheel --no-deps --no-build-isolation ...`; artifact version is `2.0.0`.
- Passed: `python3 build_macos_app.py`.
- Passed: `plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"`.
- Passed: `sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"`.
- Passed: bundled resource-module presence check.
- Passed: bundle version check (`2.0.0`).
- Passed: `git diff --check`.
- Type checking: skipped because no static type checker is configured yet.

### Notes

- API actions are now declared one operation per file inside domain packages.
  Shared authentication, pagination, audit, and error behavior stays centralized.
- The package API adapter intentionally shares the proven transport/audit implementation with the backward-compatible single-rule CLI. Resource and workflow code imports only the adapter boundary.
- No live tenant calls were made; tenant-dependent backup and restore behavior remains covered by unit fakes and existing safety tests.

## 2026-06-18

### Completed

- Added optional encrypted backup storage:
  - `--encrypt-backups` writes source, target, and restore-plan target backups as `.json.enc`.
  - Encryption uses OpenSSL-compatible `enc`, `aes-256-cbc`, PBKDF2, 200000 iterations, and SHA-256.
  - The CLI prints a standalone OpenSSL decrypt command that does not include the passphrase.
  - Backup passphrases are read from `ZPA_BACKUP_PASSPHRASE` by default or another variable selected with `--backup-passphrase-env`.
  - The OpenSSL subprocess receives only a minimal environment plus the internal passphrase variable, not tenant credential variables.
- Added transparent encrypted backup reads for validate, diff, preflight, report, restore-plan, apply, and restore.
- Added desktop UI controls for encrypted backup storage and masked passphrase entry.
- Updated README, SPEC, TASKS, and `.env.example` for encrypted backup operation and external OpenSSL decryption.
- Updated `docs/PROCESS.md` with the encrypted backup UI step, `.json.enc` artifact flow, validation behavior, and external OpenSSL decryption path.

### Checks

- Passed: `python3 -m py_compile zpa_cloner.py zpa_policy_tool.py zpa_resources.py zpa_integrity.py zpa_report.py zpa_cloner_app.py build_macos_app.py test_zpa_cloner.py test_zpa_policy_tool.py test_zpa_cloner_app.py`
- Passed: `python3 -m unittest -v` with 41 tests.
- Passed: `python3 zpa_cloner.py --help`
- Passed: `git diff --check`
- Passed: `python3 build_macos_app.py`
- Passed: `plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"`
- Passed: `sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"`
- Passed: repository secret scan for the pasted credential patterns; only placeholders and documentation terms were found.
- Type checking: skipped because no static type checker is configured yet.

### Notes

- `--encrypt-backups` encrypts backup JSON files only. Diffs, reports, restore results, and audit logs remain plaintext artifacts and must be protected separately.
- The portable OpenSSL `enc` format is not AEAD. Strict manifest validation remains the project integrity check after decryption.

## 2026-06-09

### Completed

- Added a top-priority independent-tool disclaimer:
  - Created `DISCLAIMER.md`.
  - Added a prominent README disclaimer.
  - Added a desktop UI disclaimer banner.
  - Included `DISCLAIMER.md` in the macOS app bundle resources.
  - Added the disclaimer requirement to `SPEC.md`.
  - Marked the disclaimer task complete in `TASKS.md`.
- Created first-pass project control docs:
  - `SPEC.md`
  - `TASKS.md`
  - `AGENTS.md`
  - `PROGRESS.md`
- Captured current implemented behavior from README, process docs, coverage audit, and source layout.
- Recorded current assumptions for lint and type checking.
- Removed duplicate `TASK.md`; `TASKS.md` is now the only task checklist.
- Reviewed Markdown documentation after the disclaimer push:
  - Added the disclaimer to `docs/PROCESS.md`.
  - Added the disclaimer and current policy-rule default to `ZPA_API_COVERAGE_AUDIT.md`.
  - Added an agent rule to preserve the disclaimer in future user-facing docs and UI.
  - Marked the Markdown review complete in `TASKS.md`.
- Expanded HTTP audit logging from metadata-only records to full sanitized per-call request and response records.
- Updated audit documentation to state that audit logs contain tenant configuration details and must be treated as sensitive operational records.
- Rebuilt the local macOS app bundle so the desktop app includes full-detail audit logging.

### Current Code State

- Branch at time of this documentation review: `main`.
- Documentation review corrected stale state from the earlier disclaimer work.
- Generated app bundles, backups, logs, and local env files remain ignored by Git.

### Checks

- Passed: `python3 -m py_compile zpa_cloner.py zpa_policy_tool.py zpa_resources.py zpa_integrity.py zpa_report.py zpa_cloner_app.py build_macos_app.py test_zpa_cloner.py test_zpa_policy_tool.py test_zpa_cloner_app.py`
- Passed: `python3 -m unittest -v` with 37 tests.
- Passed: `python3 build_macos_app.py`
- Passed: `plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"`
- Passed: `sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"`
- Passed: verified `dist/ZPA-Backup and Restore.app/Contents/Resources/DISCLAIMER.md` exists.
- Passed: Markdown consistency search for stale branch, test-count, old app-name, and policy default references.
- Passed after full-detail audit change: `python3 -m py_compile zpa_policy_tool.py zpa_cloner.py zpa_cloner_app.py build_macos_app.py test_zpa_policy_tool.py test_zpa_cloner.py test_zpa_cloner_app.py`
- Passed after full-detail audit change: `python3 -m unittest -v` with 37 tests.
- Passed after full-detail audit change: `python3 build_macos_app.py`
- Passed after full-detail audit change: `plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"`
- Passed after full-detail audit change: `sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"`
- Type checking: skipped because no static type checker is configured yet.

### Notes

- `TASKS.md` is canonical.
- There is no separate `TASK.md`, so there is no second checklist to keep in sync.
- `SPEC.md` should be updated before any new assumption is implemented.
