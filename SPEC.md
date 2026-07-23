# ZPA-Backup and Restore Specification

This document is the source of truth for project behavior. If a future task requires an assumption that is not already documented, update this file before implementing the task.

## Goal

Build a guarded backup, compare, restore, and migration tool for Zscaler Private Access tenants using the legacy ZPA API by default, while keeping OneAPI support available where already implemented.

Version 2 reorganizes the implementation into a maintainable Python package without weakening the existing safety model or invalidating existing operator commands.

The tool must help an operator:

- Enter source and destination tenant credentials in a desktop UI.
- Back up source and destination ZPA configuration to local JSON files.
- Compare backups and generate human-readable reports.
- Restore a destination tenant from a source backup or older snapshot.
- Validate backup integrity and run preflight checks before writes.
- Simulate restore actions before live writes.
- Record clear operator logs and durable HTTP audit logs.

## Disclaimer Requirement

- The project must prominently state that it is independent and is not affiliated with, endorsed by, sponsored by, certified by, or supported by Zscaler, Inc.
- The project must state that it is provided "as is" without warranty of any kind.
- The project must state that Zscaler does not provide support, maintenance, service-level commitment, or warranty for this tool.
- User-facing documentation and the desktop UI must keep this disclaimer visible.

## Operating Model

- Source tenant access is read-only in backup, compare, and restore-plan workflows.
- Destination tenant access is read-only until restore/apply writes are explicitly requested.
- Restore writes only to the configured destination tenant.
- A tenant can be modified only if its credentials are entered or exported as the destination profile.
- The single-rule edit CLI is separate and writes only when `--apply` is passed.

## Supported Authentication

- Legacy ZPA API is the default mode.
- OneAPI mode exists but requires ZIdentity configuration.
- Credentials must come from environment variables, `.env`, or UI fields.
- Credentials, bearer tokens, authorization headers, cookies, private keys, passwords, client secrets, tokens, and known credential fields must not be written to logs or source code.
- HTTP audit logs may contain sanitized request and response payloads for tenant API calls because they are audit evidence; treat those logs as sensitive operational records.

## Current Resource Coverage

Enabled, guarded clone resources:

- Microtenants, gated as high-impact.
- AppProtection custom controls and profiles.
- CBI banners and profiles.
- App Connector and Private Service Edge groups.
- Segment groups, application servers, and server groups.
- Application Segments, with move/share separately gated as high-impact.
- LSS configurations.
- PRA portals and consoles.
- ZPA policy rules, including deterministic bulk reorder.

Read-only reference or mapping resources:

- Identity providers, SAML attributes, SCIM attributes/values, and SCIM groups.
- Machine groups, posture profiles, and trusted networks.
- Cloud Connector groups and Browser Access groups.
- Version profiles and Zscaler clouds.
- Enrollment-certificate metadata with certificate and key fields removed.

Sanitized backup with catalog-only restore operations:

- Business Continuity settings.
- Private Cloud sites.
- Private Cloud Controller groups.

Audit-only operational inventory:

- Live Private Cloud Controllers.
- Emergency Access users.
- Privileged Approvals.

Explicitly excluded from generic cloning:

- Live App Connector instances.
- Live Private Service Edge instances.
- Certificates and private keys.
- Provisioning keys.
- Privileged credentials and other secrets.
- Tenant-administration and other operational lifecycle actions that do not
  represent portable tenant configuration.

## API Operation Catalog And Coverage Expansion

- API coverage must be represented by small declarative operation modules grouped
  under a resource/domain package. One operation module represents one documented
  HTTP action and declares its method, path, role, pagination behavior, safety
  classification, and documentation slug.
- Resource/domain modules compose operation declarations and own dependency,
  identity, payload, and restore behavior. Authentication, request execution,
  pagination, auditing, redaction, retries, and error handling remain shared.
- Coverage output must distinguish `clone`, `reference`, `audit`, and `excluded`
  modes and must report explicit operations rather than infer CRUD support from a
  writable flag.
- Read-only restore references must include SAML attributes, version profiles,
  Zscaler clouds, enrollment-certificate metadata, Cloud Connector groups, and
  Browser Access groups. Certificate bodies and private keys must not be stored.
- Policy coverage must include `PRIVILEGED_PORTAL_POLICY`. Restore must preserve
  policy evaluation order through the documented reorder operation after rule
  creates and updates.
- Application Segment move and share endpoints must be modeled as high-impact
  special operations. They may execute only when target Microtenant and dependency
  IDs resolve unambiguously; otherwise simulation and restore must block them.
- Business Continuity settings, Private Clouds/Sites, and Private Cloud Controller
  groups are high-impact clone domains. Live Private Cloud Controllers remain
  audit-only inventory.
- Emergency Access users and Privileged Approvals are audit-only because their
  activation and time-window semantics are operational state, not ordinary tenant
  configuration.
- Provisioning keys, privileged credentials, private keys, and other secrets
  remain excluded even when the API documents write operations.

## Backup Requirements

- Backups must include `meta`, `resources`, `errors`, `warnings`, and a manifest.
- The manifest must include schema version, customer ID, timestamp, policy types, resource counts, error count, endpoint error keys, and SHA-256 checksum.
- Backups must include all modeled non-policy resources.
- Policy rule type checkboxes affect policy rules only, not application segments or dependency resources.
- Application segment backup should use the paginated `GET /application` list endpoint directly because it returns detailed records.
- Pagination must use the maximum practical page size currently configured as `pagesize=500`.
- Backup writers may optionally store source and destination backup JSON files as OpenSSL-compatible `.json.enc` files.
- Encrypted backup files must be readable by validate, diff, preflight, report, restore-plan, and restore workflows when the passphrase is available.
- Backup encryption passphrases must come from an environment variable or masked UI field and must not be written to source code, audit logs, or operator command lines.
- Encrypted backup documentation must include a direct OpenSSL decrypt command so operators can decrypt a backup without this tool.

## Diff And Restore Requirements

- Diffs must compare resources by stable name-based identity, with policy rules also scoped by policy type.
- Tenant-specific IDs and system fields must not create false update diffs.
- Restore must create and update resources in dependency order.
- Restore deletes must be skipped by default and allowed only with `--allow-delete`.
- Deletes must run in reverse dependency order.
- High-impact writes, including Microtenants and Application Segment move/share
  operations, must be skipped by default and allowed only with
  `--allow-high-impact`.
- Restore must require explicit confirmation through `--yes`; simulation never writes.
- Special restore operations must appear in the deterministic simulation artifact
  and use the same high-impact, reviewed-plan, drift, journal, and post-restore
  verification controls as ordinary CRUD operations.

## Restore Simulation Requirements

- Restore simulation must be a deterministic offline operation over the selected source backup, target backup, and diff; it must not require tenant credentials or make HTTP requests.
- `simulate` is the canonical command. `restore --dry-run` and `apply --dry-run` remain compatibility aliases for the same simulator.
- Simulation must apply the same delete and high-impact safeguards as a live restore and clearly group skipped operations by reason.
- Simulation must list operations in live execution order with the intended HTTP method, target path, sanitized request body, dependency metadata, source ID, target ID, and sequence number.
- Known cross-tenant IDs must be remapped in simulated payloads.
- IDs that will be returned only after an earlier planned create must be represented as explicit deferred references rather than source-tenant IDs.
- Unmapped source IDs, missing target IDs, and missing target policy sets must block the affected operation and be reported with field paths before live writes.
- Simulation must write reviewable JSON and HTML artifacts and include summary counts for planned, skipped, blocked, deferred, and unresolved operations.
- Simulation artifacts must redact sensitive-looking payload fields using the same report redaction policy.

## Validation And Preflight Requirements

- Validate must check backup structure, diff structure, manifest presence when strict mode is requested, schema version, and manifest checksum.
- Preflight must check source and destination customer ID consistency, backup endpoint errors, diff shape, and declared dependency order.
- Preflight must block restore unless the operator explicitly allows failed backups with `--allow-failed-backups`.

## Logging And Audit Requirements

- CLI and UI output must show high-level stage progress.
- API progress lines must show the current method/path/query before a request is made, so a stuck request is visible.
- HTTP audit logs must be written as ignored JSON lines under `logs/` by default.
- Audit logs must record each API call with method, sanitized URL, query parameters, sanitized request headers, sanitized request body, response status, duration, sanitized response headers, response bytes, response shape, record counts, and sanitized response body.
- Audit logs must not write bearer tokens, authorization headers, cookies, client secrets, passwords, private keys, tokens, certificates, or known credential fields.
- Error bodies may be logged only when sanitized.

## UI Requirements

- The desktop UI must provide source and destination credential tabs.
- The UI must show workflow controls for backup, compare, restore-plan, validate,
  preflight, simulate, restore, report, and coverage.
- The UI must stream CLI output into the Activity panel.
- The UI must capture generated artifact paths, including backups, diffs, reports, restore results, and audit logs.
- The UI must keep secrets masked unless the operator explicitly toggles visibility.
- The left-side controls must fit at the minimum supported window size without
  vertical scrolling. Group configuration into focused tabs while keeping the
  workflow order and safety boundaries visible.
- The UI must provide a focused restore-scope tab for canonical object
  selectors, whole writable resource types, explicit dependency inclusion, and
  explicit policy-order restoration.
- The UI must provide concise contextual tooltips for navigation tabs,
  workflow actions, technical fields, artifacts, and restore safeguards.
  Tooltips must be available through pointer hover and keyboard focus, and
  visible labels must remain sufficient to operate the tool without them.

## macOS App Requirements

- The app name is `ZPA-Backup and Restore`.
- Runtime data for the bundled app must live under `~/Documents/ZPA-Backup and Restore`.
- On Apple Silicon, the launcher must avoid Intel-only Python binaries and shell shims that would trigger Rosetta.
- The bundle must use a native Python 3 with Tkinter.

## Verification Requirements

Use the closest available checks for each change:

- Syntax/lint equivalent: `python3 -m py_compile ...`.
- Type checking: no static type checker is configured yet. Until one is added, document this as skipped.
- Tests: `python3 -m unittest -v`.
- App build checks when UI or bundle files change: `python3 build_macos_app.py`, `plutil -lint`, and `sh -n` on the launcher.

## Version 2 Architecture And Compatibility

- The maintained implementation must live under the `zpa_backup_restore` package.
- Package boundaries must separate resource catalog, backup storage, diffing, identity mapping, restore execution, integrity checks, reporting, CLI orchestration, and UI concerns.
- Each modeled ZPA resource or closely related API domain must have a composition
  module for dependencies, identity, payload, safety flags, and exceptional
  behavior. Each modeled HTTP action must have a small declarative operation
  module inside the corresponding domain package. Shared HTTP mechanics such as
  authentication, pagination, auditing, retries, and error normalization must
  not be duplicated per action.
- Pure transformation logic such as diffing, mapping, integrity checks, and report rendering must remain independently testable without tenant credentials or network access.
- `python3 -m zpa_backup_restore` is the canonical v2 CLI entry point.
- Installed distributions must expose a `zpa-backup-restore` console command.
- Existing `zpa_cloner.py`, `zpa_policy_tool.py`, `zpa_resources.py`, `zpa_integrity.py`, and `zpa_report.py` imports and script commands remain compatibility surfaces during the v2 transition.
- Version 2 keeps the current backup manifest schema at `1.0`; a code-layout release alone must not make existing backups unreadable.
- Runtime behavior stays Python-standard-library-only. Packaging and development tooling may use the Python build ecosystem without becoming runtime dependencies.
- The macOS app bundle must include the `zpa_backup_restore` package and report the same release version as the Python package.

## Managed Snapshot And Inventory Requirements

- Snapshot, inventory, audit, and restore-assurance behavior must be implemented as application services behind repository interfaces; CLI and UI code must remain adapters.
- The default local catalog must use Python's standard-library SQLite support under `state/catalog.sqlite3` with explicit schema migrations.
- Snapshot IDs must be content-derived, and catalog records must include artifact SHA-256, manifest checksum, tenant fingerprint, capture time, encryption state, counts, warnings, errors, and verification state.
- Tenant fingerprints must be one-way hashes of customer IDs; the catalog must not store credentials, tokens, secrets, or complete resource payloads.
- The inventory index may store resource type, stable identity, display name, source object ID, normalized configuration hash, write/safety classification, and reference edges. Treat the catalog as sensitive operational data and create it with restrictive file permissions.
- Existing backup, plan, and restore-plan workflows must register generated snapshots automatically. Existing backup files must be importable without tenant access.
- Inventory commands must support snapshot listing, inspection, verification, resource search, history, reference lookup, and JSON/CSV export without tenant credentials.

## Run Audit Ledger Requirements

- A run-level append-only JSONL ledger must complement the detailed HTTP audit log.
- Ledger events must include a run ID, command, timestamps, result, application version, safeguard selections, input/output artifact hashes, and HTTP audit-log hash without secrets.
- Events must use a SHA-256 hash chain so accidental modification, removal, or reordering is detectable. Documentation must describe this as tamper-evident, not tamper-proof.
- Audit commands must support listing runs, failure summaries, command summaries, detailed run inspection, and chain verification.

## Restore Assurance Requirements

- Simulation artifacts must contain deterministic hashes for source backup, reviewed target backup, diff, normalized target state, and the complete ordered plan.
- Live restore must require the reviewed simulation artifact by default. A compatibility bypass must be explicit and auditable.
- Before writes, live restore must verify the simulation hash, its input hashes, selected safeguards, and absence of blocking operations.
- Before writes, the tool must capture a fresh destination snapshot and refuse a stale plan when normalized destination state differs from the reviewed target state.
- Restore must record an execution journal and capture a post-restore destination snapshot.
- Post-restore verification must produce a residual diff and report. Remaining differences must not be silently described as success.

## Selective Restore Requirements

- Operators must be able to restore one named resource, several named resources,
  or an entire writable resource type without editing backup or diff JSON.
- Individual selection must use a stable tenant-independent identity. Policy-rule
  identity must include policy type and normalized rule name; tenant-specific
  source or destination IDs must not be the primary selector.
- Selective scope must be created while producing the diff and persisted in that
  artifact. Simulation, reviewed-plan assurance, fresh-target drift protection,
  execution journals, and post-restore residual verification must all use the
  same persisted scope.
- A selector that is invalid, unsupported, missing from the desired backup, or
  ambiguous must block planning with a clear error before destination credentials
  are used for writes.
- Dependency objects must not be changed implicitly. Operators may explicitly
  request recursive inclusion of missing writable dependencies; read-only or
  unresolved dependencies must continue to block simulation.
- Policy-rule bulk reorder must be excluded from an individual selective restore
  unless the operator explicitly requests policy-order restoration.
- Inventory output must expose canonical selectors and a copyable restore-plan
  command for writable resources.
- Selective post-restore verification must judge only the selected scope so
  unrelated tenant differences do not turn a successful targeted recovery into
  a false failure.

## Disaster Recovery Runbook Requirements

- Operators must be able to generate a credential-free disaster-recovery
  runbook from an existing plain or encrypted backup artifact.
- The runbook must have a canonical JSON artifact for automation and audit plus
  a printable HTML report for human execution.
- The runbook must enumerate every resource object captured in the selected
  backup, every modeled API domain including empty or failed domains, and every
  explicitly known recovery exclusion. It must not describe current coverage as
  complete ZPA platform coverage when unmodeled or excluded settings remain.
- Each captured object must have a stable checklist ID, display name, resource
  type, stable identity, restore capability, safety classification,
  dependencies, ordered instructions, and either an exact selective
  `restore-plan` command or an explicit manual/reference-only procedure.
- Clone-capable resources may use the guarded selective-restore workflow.
  Reference, audit-only, catalog-only, secret-bearing, ambiguous, and excluded
  resources must never receive a misleading automated restore command.
- Global readiness, change-control, destination verification, residual-diff,
  business validation, ledger verification, and evidence-archive steps must be
  included around the per-setting checklist.
- Checklist changes must record timestamp, operator, previous and new status,
  evidence reference, and note. Completion and not-applicable decisions require
  evidence.
- The immutable plan, mutable checklist state, and checklist event chain must
  use deterministic SHA-256 hashes so accidental modification, removal, or
  reordering is detectable. This is tamper-evident, not tamper-proof.
- Runbook generation, status, checklist updates, HTML regeneration, and
  verification must be available without tenant credentials. These commands
  must also participate in the existing run audit ledger.
- The desktop UI must expose runbook generation from the selected desired
  backup, capture both runbook artifacts, and provide a direct way to open the
  HTML checklist without adding vertical scrolling.
- Runbooks contain tenant configuration names, artifact paths, operator names,
  and evidence references. They must be treated as sensitive operational
  records and written with restrictive permissions where supported.

## Assumptions

- No dedicated lint tool is currently configured; `compileall` is the project lint substitute for now.
- No dedicated type checker is currently configured; type checking is skipped until a tool such as mypy or pyright is added.
- The Zscaler API documentation can change. Re-check official docs before broadening API coverage or changing endpoint semantics.
- Restore safety is more important than breadth of API coverage.
- Encrypted backups use OpenSSL `enc` with `aes-256-cbc`, PBKDF2, 200000 iterations, and SHA-256 because it is available without adding a Python package dependency and can be decrypted outside the tool. This portable format is not AEAD; strict manifest validation remains the integrity check after decryption.
