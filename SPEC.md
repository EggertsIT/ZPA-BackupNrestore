# ZPA-Backup and Restore Specification

This document is the source of truth for project behavior. If a future task requires an assumption that is not already documented, update this file before implementing the task.

## Goal

Build a guarded backup, compare, restore, and migration tool for Zscaler Private Access tenants using the legacy ZPA API by default, while keeping OneAPI support available where already implemented.

The tool must help an operator:

- Enter source and destination tenant credentials in a desktop UI.
- Back up source and destination ZPA configuration to local JSON files.
- Compare backups and generate human-readable reports.
- Restore a destination tenant from a source backup or older snapshot.
- Validate backup integrity and run preflight checks before writes.
- Dry-run restore actions before live writes.
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

Writable or restore-modeled resources:

- Microtenants, gated as high-impact.
- Inspection custom controls.
- Inspection profiles.
- CBI profiles.
- App connector groups.
- Service edge groups.
- Segment groups.
- Servers.
- Server groups.
- Application segments.
- LSS configurations.
- PRA portals.
- PRA consoles.
- ZPA policy rules.

Read-only reference or inventory resources:

- CBI banners.
- Machine groups.
- Posture profiles.
- Trusted networks.
- IdPs.
- SCIM attributes.
- SCIM groups.

Explicitly excluded from generic cloning:

- Live App Connector instances.
- Live Private Service Edge instances.
- Certificates and private keys.
- Provisioning keys.
- Privileged credentials and other secrets.

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
- Microtenant writes must be skipped by default and allowed only with `--allow-high-impact`.
- Restore must require explicit confirmation through `--yes`, except dry-run mode.

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
- The UI must show workflow controls for backup, compare, restore-plan, validate, preflight, dry-run, restore, report, and coverage.
- The UI must stream CLI output into the Activity panel.
- The UI must capture generated artifact paths, including backups, diffs, reports, restore results, and audit logs.
- The UI must keep secrets masked unless the operator explicitly toggles visibility.

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

## Assumptions

- No dedicated lint tool is currently configured; `py_compile` is the project lint substitute for now.
- No dedicated type checker is currently configured; type checking is skipped until a tool such as mypy or pyright is added.
- The Zscaler API documentation can change. Re-check official docs before broadening API coverage or changing endpoint semantics.
- Restore safety is more important than breadth of API coverage.
- Encrypted backups use OpenSSL `enc` with `aes-256-cbc`, PBKDF2, 200000 iterations, and SHA-256 because it is available without adding a Python package dependency and can be decrypted outside the tool. This portable format is not AEAD; strict manifest validation remains the integrity check after decryption.
