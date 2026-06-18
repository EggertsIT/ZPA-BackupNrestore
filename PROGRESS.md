# Progress

This file records completed work, verification, skipped checks, and known risks. Update it after each task from `TASKS.md`.

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
