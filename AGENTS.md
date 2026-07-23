# Agent Instructions

This project uses `SPEC.md`, `TASKS.md`, and `PROGRESS.md` to keep work scoped, testable, and auditable.

## Working Loop

1. Read `SPEC.md`.
2. Read `TASKS.md`.
3. When the user specifies a scope, select the matching checklist item. Otherwise,
   choose the next unchecked task in the active milestone that is not blocked by
   an earlier dependency.
4. Implement only that task.
5. Write or update tests for the task.
6. Run the relevant checks:
   - Syntax/lint substitute: `python3 -m compileall -q zpa_backup_restore *.py`
   - Type checking: currently not configured; record as skipped in `PROGRESS.md`.
   - Tests: `python3 -m unittest -v` or a narrower relevant test command.
   - macOS bundle checks when app packaging changes: `python3 build_macos_app.py`, `plutil -lint`, and `sh -n` for the launcher.
7. If any check fails, fix it before moving on.
8. Update `TASKS.md` by checking completed task boxes.
9. Update `PROGRESS.md` with what changed, checks run, skipped checks, and any follow-up risk.
10. Repeat until all tasks are complete or the next task is blocked.

## If Unsure

1. Check `SPEC.md` first.
2. Check `TASKS.md` second.
3. Do not invent new requirements unless necessary.
4. If a reasonable assumption is required, document it in `SPEC.md` before implementing.
5. If the assumption could affect tenant safety, restore behavior, credentials, or logging, stop and ask for confirmation.

## Project Rules

- Protect source tenants. Backup, compare, and restore-plan operations must not write to source.
- Treat the configured destination tenant as the only restore write target.
- Never write client secrets, bearer tokens, authorization headers, cookies, private keys, passwords, tokens, certificates, or known credential fields to logs or source files.
- HTTP audit logs intentionally contain sanitized request and response payloads for tenant API calls; treat them as sensitive operational records.
- Keep generated backups, logs, reports, local `.env` files, and app bundles ignored by Git.
- Prefer conservative restore behavior: no deletes by default, high-impact resources gated, preflight and offline simulation before live restore.
- Keep changes small and aligned with existing stdlib-only Python patterns.
- Avoid broad refactors while implementing a checklist task.
- Update tests when behavior changes.
- Update documentation when operator behavior, safety boundaries, or API coverage changes.
- Keep the independent-tool, no-Zscaler-support, no-warranty disclaimer visible in user-facing documentation and the desktop UI.
- Do not claim full ZPA API compliance unless `ZPA_API_COVERAGE_AUDIT.md` and implementation prove it.

## Current Tooling

- Runtime: Python 3 standard library.
- UI: Tkinter.
- Tests: `unittest`.
- App bundle: `build_macos_app.py`.
- Lint substitute: `python3 -m py_compile`.
- Type checker: not configured yet.

## Common Commands

```sh
python3 -m compileall -q zpa_backup_restore *.py
python3 -m unittest -v
python3 -m zpa_backup_restore --help
python3 build_macos_app.py
plutil -lint "dist/ZPA-Backup and Restore.app/Contents/Info.plist"
sh -n "dist/ZPA-Backup and Restore.app/Contents/MacOS/zpa-backup-restore"
```
