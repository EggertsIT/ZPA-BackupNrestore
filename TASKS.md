# Tasks

This file is the canonical checklist for the project. Checked items are
implemented and verified; unchecked items are explicit future work, not claims
about current behavior. Follow an explicitly requested scope first. Otherwise,
work from top to bottom within the active milestone unless `SPEC.md` says a
different order is required. Keep each task small enough to implement, test,
and review independently.

## 0. Project Control Docs

- [x] Create `SPEC.md` with project goals, safety boundaries, and current assumptions.
- [x] Create `TASKS.md` with small, checkable implementation tasks.
- [x] Create `AGENTS.md` with the working loop and project rules.
- [x] Create `PROGRESS.md` with initial project status.
- [x] Remove duplicate `TASK.md`; use `TASKS.md` as the only task checklist.
- [x] Add mandatory no-affiliation, no-support, no-warranty disclaimer requirement.

## 1. Safety And Validation

- [x] Ensure source-to-destination workflow treats source as read-only.
- [x] Require explicit confirmation for restore writes.
- [x] Skip deletes by default.
- [x] Gate high-impact microtenant writes.
- [x] Add strict manifest validation.
- [x] Add restore preflight checks.
- [x] Add optional encrypted backup storage with OpenSSL-compatible external decryption.
- [ ] Add a preflight check that reports unresolved named dependencies before writes.
- [ ] Add a preflight check that flags read-only reference mismatches by resource type.
- [x] Add a simulation summary that groups skipped writes by reason.

## 2. Backup Coverage

- [x] Back up core dependency resources: connector groups, service edge groups, segment groups, servers, and server groups.
- [x] Back up application segments.
- [x] Optimize application segment backup to use the paginated `GET /application` list response.
- [x] Back up all supported policy rule types by default.
- [x] Back up IdP, SCIM attribute, and SCIM group references for ID mapping.
- [x] Add guarded CBI banner CRUD plus read-only inventory for machine groups,
  posture profiles, and trusted networks.
- [x] Read encrypted `.json.enc` backups in validate, diff, preflight, report, restore-plan, and restore workflows.
- [x] Add read-only SAML attribute inventory and mapping.
- [x] Add read-only version profile inventory.
- [x] Add read-only Zscaler cloud inventory.
- [x] Add read-only enrollment certificate inventory without private key handling.
- [x] Add read-only cloud connector group inventory.

## 3. Diff And Restore Behavior

- [x] Compare resources by stable name-based identity.
- [x] Scope policy rule identity by policy type and name.
- [x] Remap dependency IDs from source backup to destination tenant objects.
- [x] Create and update resources in declared dependency order.
- [x] Delete resources in reverse dependency order.
- [ ] Ignore all known write-skip fields during compare when those fields are derived or embedded read-only data.
- [x] Add policy rule reorder support where the ZPA API requires a separate reorder operation.
- [x] Add application segment share/move operation support only after explicit spec update.

## 4. Logging And Audit

- [x] Add high-level CLI run banners and resource counts.
- [x] Add UI status parsing for backup and restore progress lines.
- [x] Add per-request API progress lines before and after each HTTP call.
- [x] Add JSONL HTTP audit logs under ignored `logs/`.
- [x] Redact secrets and tokens from audit output.
- [x] Add UI capture and Open Log support for audit logs.
- [x] Log full sanitized request and response details for each API call.
- [x] Add audit-log retention guidance to README or docs.
- [ ] Add an audit-log summary command that prints slowest calls and failed calls.
- [ ] Add timeout-specific error messages that identify the last in-flight endpoint.

## 5. UI

- [x] Provide source and destination credential tabs.
- [x] Keep secret fields masked by default.
- [x] Make policy rule scope a checkbox list.
- [x] Make non-policy resources always included in backup.
- [x] Add restore-from-past-snapshot workflow controls.
- [x] Add activity panel output streaming.
- [x] Add artifact fields for backups, diff, reports, restore result, and audit log.
- [x] Add UI controls for encrypted backup storage and passphrase entry.
- [x] Replace the vertically scrolling left control stack with a compact,
  tabbed layout that fits at the minimum window size.
- [x] Add pointer- and keyboard-accessible contextual tooltips for navigation,
  workflow actions, technical fields, artifacts, and restore safeguards.
- [ ] Add a UI command to open the runtime work directory.
- [ ] Add a UI command to open the latest backup folder.
- [ ] Add visible command duration for completed runs.

## 6. macOS App

- [x] Rename app to `ZPA-Backup and Restore`.
- [x] Build a lightweight macOS `.app` wrapper.
- [x] Store app runtime files under `~/Documents/ZPA-Backup and Restore`.
- [x] Avoid Apple Silicon Rosetta prompts by skipping Intel-only Python binaries and shims.
- [x] Add a release packaging checklist.
- [x] Add a clean version bump process for app releases.

## 7. Tests And Tooling

- [x] Add unit tests for backup/diff/restore helper behavior.
- [x] Add unit tests for UI helper parsing.
- [x] Add unit tests for single-rule SCIM condition edits.
- [x] Add tests for application segment fast backup call behavior.
- [x] Add tests for audit logger redaction and full sanitized request/response details.
- [x] Add tests for OpenSSL-compatible encrypted backup round-trip and external decrypt.
- [ ] Add a configured lint command.
- [ ] Add a configured type checking command.
- [ ] Add a smoke test command that exercises CLI help, coverage, validate, and report paths.

## 8. Documentation

- [x] Document the main CLI workflow in README.
- [x] Document the graphical process in `docs/PROCESS.md`.
- [x] Document current ZPA API coverage limitations.
- [x] Document audit log behavior.
- [x] Add prominent independent-tool, no-Zscaler-support, no-warranty disclaimer.
- [x] Review Markdown docs after the disclaimer/main push and correct stale state.
- [x] Document encrypted backup storage and standalone OpenSSL decryption.
- [x] Document exact source-read and destination-write boundaries in README.
- [x] Document production rehearsal steps using a lab tenant.
- [x] Document known unsupported ZPA API sections and why they are excluded.

## 9. GitHub And Release Hygiene

- [x] Keep backups, logs, local env files, and app bundles out of Git.
- [x] Confirm and document the branch strategy before committing feature work.
- [x] Add pull request checklist.
- [x] Add release checklist for macOS app distribution.
- [x] Add guidance to rotate any credentials accidentally pasted into chat or logs.

## 10. Version 2 Maintainability

- [x] Define v2 architecture and backward-compatibility requirements in `SPEC.md`.
- [x] Add a versioned `zpa_backup_restore` Python package with a canonical module entry point.
- [x] Move the resource catalog and integrity checks behind package modules.
- [x] Split the resource catalog into one maintainable module per ZPA resource or closely related API domain.
- [x] Separate backup file encryption and JSON storage from CLI orchestration.
- [x] Separate pure diff and identity mapping logic from CLI orchestration.
- [x] Separate guarded restore execution from CLI orchestration.
- [x] Move HTML reporting behind a package module.
- [x] Keep legacy modules and scripts as documented compatibility façades.
- [x] Add package metadata and an installed `zpa-backup-restore` console command.
- [x] Include the package in the macOS app bundle and align bundle/package versions.
- [x] Add architecture, module-entry-point, and compatibility tests.
- [x] Document the v2 source tree and extension workflow.

## 11. High-Value Restore Simulation

- [x] Specify offline simulation behavior and safety parity in `SPEC.md`.
- [x] Add deterministic ordered restore-operation planning without a tenant client.
- [x] Include HTTP methods, target paths, sanitized payloads, dependencies, and IDs in simulation artifacts.
- [x] Represent IDs from planned creates as deferred references.
- [x] Block and report unresolved source IDs, missing target IDs, and missing policy sets.
- [x] Apply high-impact and delete safeguards exactly as live restore would.
- [x] Group skipped operations by reason and summarize planned, skipped, blocked, deferred, and unresolved counts.
- [x] Add a credential-free `simulate` command and preserve `restore --dry-run` as an alias.
- [x] Generate dedicated simulation JSON and HTML artifacts.
- [x] Update desktop UI artifact capture and remove the destination-credential requirement for simulation.
- [x] Add simulation, CLI, report, and UI tests.
- [x] Update operator and architecture documentation.

## 12. Managed Recovery Platform

- [x] Specify managed snapshot, inventory, audit-ledger, and restore-assurance requirements.
- [x] Add domain models and repository protocols independent of CLI, UI, and SQLite.
- [x] Add a versioned SQLite catalog with restrictive permissions and migrations.
- [x] Register and verify existing or newly generated backup artifacts.
- [x] Index safe resource metadata and generic cross-resource reference edges without storing payloads.
- [x] Add snapshot list/import/show/verify commands.
- [x] Add inventory list/search/history/references/export commands.
- [x] Add inventory drift summaries across snapshots.
- [x] Add a hash-chained run audit ledger and run correlation IDs.
- [x] Add audit list/show/summary/failures/verify commands.
- [x] Add deterministic simulation input, target-state, and plan hashes.
- [x] Require a matching reviewed simulation for live restore unless an explicit audited compatibility bypass is used.
- [x] Capture a fresh pre-restore destination snapshot and block stale target state before writes.
- [x] Add an execution journal, post-restore snapshot, residual diff, and verification report.
- [x] Add focused repository, migration, inventory, ledger, assurance, and CLI tests.
- [x] Update the desktop UI for snapshot, inventory, restore assurance, and audit workflows.
- [x] Update operator, architecture, security, retention, and recovery documentation.

## 13. ZPA API Coverage Expansion

- [x] Add the declarative per-operation contract and domain-package composition.
- [x] Convert modeled resources from inferred CRUD to explicit operation coverage.
- [x] Add SAML attribute inventory and scoped cross-tenant mapping.
- [x] Add version profile, Zscaler cloud, enrollment-certificate metadata, Cloud
  Connector group, and Browser Access group reference inventory.
- [x] Add `PRIVILEGED_PORTAL_POLICY` and deterministic policy-rule reordering.
- [x] Model and safely plan Application Segment move/share operations.
- [x] Catalog and safely back up sanitized Business Continuity, Private Cloud/Site,
  and Private Cloud Controller group configuration.
- [ ] Add high-impact Business Continuity, Private Cloud/Site, and Private Cloud
  Controller group restore after two-phase associations and secret injection are designed.
- [x] Add audit-only live Private Cloud Controller, Emergency Access user, and
  Privileged Approval inventory.
- [x] Make coverage output report mode, sensitivity, and explicit operations.
- [x] Refresh the API coverage audit from the current official ZPA sitemap.
- [x] Add focused endpoint, mapping, simulation, restore, coverage, and
  backward-compatibility tests.
- [x] Run compile, unit, CLI coverage, package, and diff checks and record results.

## 14. Selective Restore

- [x] Add canonical stable selectors for individual resources and whole writable
  resource types.
- [x] Build scoped diffs without requiring operators to edit JSON artifacts.
- [x] Add explicit recursive inclusion for referenced writable dependencies.
- [x] Carry scope through simulation assurance, fresh-target drift checks, live
  execution, and scoped post-restore verification.
- [x] Keep policy reordering opt-in for selective policy-rule restore.
- [x] Print canonical selectors and copyable restore-plan commands from inventory.
- [x] Add CLI, scope, dependency, assurance, and regression tests.
- [x] Document the selective restore workflow, safety boundaries, and limitations.

## 15. Disaster Recovery Runbook

- [x] Define a versioned, tamper-evident DR runbook and checklist schema.
- [x] Inventory every captured object, modeled domain, backup failure, and known
  external recovery gap.
- [x] Generate exact selective restore-plan commands only for safely supported
  resources and explicit manual procedures for all other modes.
- [x] Add readiness, change-control, destination, post-restore, business
  validation, ledger, and evidence-archive checklist phases.
- [x] Add credential-free generate, status, check, report, and verify CLI
  commands with run-ledger artifact recording.
- [x] Generate printable HTML with status summaries, ordered procedures,
  per-setting checkboxes, commands, evidence, and integrity metadata.
- [x] Add a compact desktop action plus runbook JSON/HTML artifact capture and
  direct report opening.
- [x] Add schema, coverage, command, audit-chain, tamper, CLI, report, and UI
  tests.
- [x] Document DR operation, audit limitations, security, and recovery coverage
  boundaries.
