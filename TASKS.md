# Tasks

This file is the canonical checklist for the project. Work from top to bottom unless `SPEC.md` says a different order is required. Keep each task small enough to implement, test, and review independently.

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
- [ ] Add a preflight check that reports unresolved named dependencies before writes.
- [ ] Add a preflight check that flags read-only reference mismatches by resource type.
- [ ] Add a dry-run summary that groups skipped writes by reason.

## 2. Backup Coverage

- [x] Back up core dependency resources: connector groups, service edge groups, segment groups, servers, and server groups.
- [x] Back up application segments.
- [x] Optimize application segment backup to use the paginated `GET /application` list response.
- [x] Back up all supported policy rule types by default.
- [x] Back up IdP, SCIM attribute, and SCIM group references for ID mapping.
- [x] Include read-only inventory for CBI banners, machine groups, posture profiles, and trusted networks.
- [ ] Add read-only SAML attribute inventory and mapping.
- [ ] Add read-only version profile inventory.
- [ ] Add read-only Zscaler cloud inventory.
- [ ] Add read-only enrollment certificate inventory without private key handling.
- [ ] Add read-only cloud connector group inventory.

## 3. Diff And Restore Behavior

- [x] Compare resources by stable name-based identity.
- [x] Scope policy rule identity by policy type and name.
- [x] Remap dependency IDs from source backup to destination tenant objects.
- [x] Create and update resources in declared dependency order.
- [x] Delete resources in reverse dependency order.
- [ ] Ignore all known write-skip fields during compare when those fields are derived or embedded read-only data.
- [ ] Add policy rule reorder support where the ZPA API requires a separate reorder operation.
- [ ] Add application segment share/move operation support only after explicit spec update.

## 4. Logging And Audit

- [x] Add high-level CLI run banners and resource counts.
- [x] Add UI status parsing for backup and restore progress lines.
- [x] Add per-request API progress lines before and after each HTTP call.
- [x] Add JSONL HTTP audit logs under ignored `logs/`.
- [x] Redact secrets and tokens from audit output.
- [x] Add UI capture and Open Log support for audit logs.
- [ ] Add audit-log retention guidance to README or docs.
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
- [ ] Add a UI command to open the runtime work directory.
- [ ] Add a UI command to open the latest backup folder.
- [ ] Add visible command duration for completed runs.

## 6. macOS App

- [x] Rename app to `ZPA-Backup and Restore`.
- [x] Build a lightweight macOS `.app` wrapper.
- [x] Store app runtime files under `~/Documents/ZPA-Backup and Restore`.
- [x] Avoid Apple Silicon Rosetta prompts by skipping Intel-only Python binaries and shims.
- [ ] Add a release packaging checklist.
- [ ] Add a clean version bump process for app releases.

## 7. Tests And Tooling

- [x] Add unit tests for backup/diff/restore helper behavior.
- [x] Add unit tests for UI helper parsing.
- [x] Add unit tests for single-rule SCIM condition edits.
- [x] Add tests for application segment fast backup call behavior.
- [x] Add tests for audit logger redaction and response metadata.
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
- [ ] Document exact source-read and destination-write boundaries in README.
- [ ] Document production rehearsal steps using a lab tenant.
- [ ] Document known unsupported ZPA API sections and why they are excluded.

## 9. GitHub And Release Hygiene

- [x] Keep backups, logs, local env files, and app bundles out of Git.
- [ ] Confirm branch strategy before committing feature work.
- [ ] Add pull request checklist.
- [ ] Add release checklist for macOS app distribution.
- [ ] Add guidance to rotate any credentials accidentally pasted into chat or logs.
