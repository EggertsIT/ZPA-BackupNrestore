## Outcome

Describe the operator-visible result and the problem it solves.

## Safety impact

- [ ] Source workflows remain read-only.
- [ ] Restore writes only to the configured destination.
- [ ] Deletes and high-impact operations remain explicitly gated.
- [ ] Secrets and sensitive fields remain redacted from persisted output.
- [ ] New or changed API operations have an explicit support classification.
- [ ] No real credentials, tenant backups, logs, reports, or customer data are
      included in this pull request.

## Verification

- [ ] `python3 -m compileall -q zpa_backup_restore *.py`
- [ ] `python3 -m unittest discover -v`
- [ ] Relevant CLI help and coverage commands
- [ ] `git diff --check`
- [ ] macOS bundle checks, or not applicable
- [ ] Live lab-tenant rehearsal, or explicitly documented as not performed

## Documentation

- [ ] `SPEC.md` updated when behavior or safety requirements changed
- [ ] `TASKS.md` and `PROGRESS.md` updated
- [ ] README/operator/architecture documentation updated where applicable
- [ ] `ZPA_API_COVERAGE_AUDIT.md` updated when endpoint coverage changed

## Residual risk

List known limitations, deferred work, and rollback considerations.
