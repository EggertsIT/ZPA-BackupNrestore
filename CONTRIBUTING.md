# Contributing

ZPA-Backup and Restore handles security-sensitive tenant configuration. Changes
must preserve the source-read-only boundary, destination-only writes, secret
redaction, explicit confirmation, and conservative restore defaults described
in [SPEC.md](SPEC.md).

## Branch Strategy

`main` is the releasable branch. Use short-lived branches named
`feature/<topic>`, `fix/<topic>`, or `docs/<topic>` and merge them through a
reviewed pull request. Keep each branch focused on one checklist item or one
cohesive fix. Do not combine unrelated formatting, refactoring, and behavior
changes.

Release tags use `vMAJOR.MINOR.PATCH` and must point to a commit that has passed
the release checklist in [docs/RELEASE.md](docs/RELEASE.md).

## Working Agreement

1. Read [SPEC.md](SPEC.md), then [TASKS.md](TASKS.md).
2. Select an unblocked checklist item or document the new requirement before
   implementation.
3. Keep endpoint facts in one declarative operation module under
   `zpa_backup_restore/resources/operations/<domain>/`.
4. Keep domain-specific identity, dependency, payload, and safety behavior in
   the composing resource module.
5. Reuse the shared transport, pagination, audit, redaction, diff, mapping, and
   restore services.
6. Add tests proportional to the change and update operator-facing
   documentation whenever behavior, risk, artifacts, or API coverage changes.
7. Record completed work, checks, skipped checks, and remaining risk in
   [PROGRESS.md](PROGRESS.md).

## Required Checks

Run the checks relevant to the change:

```sh
python3 -m compileall -q zpa_backup_restore *.py
python3 -m unittest discover -v
python3 -m zpa_backup_restore --help
python3 -m zpa_backup_restore coverage
git diff --check
```

For packaging or desktop-app changes, also follow
[docs/RELEASE.md](docs/RELEASE.md). No static type checker is currently
configured; record type checking as skipped rather than claiming it passed.

## API Coverage Changes

An API coverage change is complete only when:

- the official endpoint is represented by a dedicated `OperationSpec` module;
- support is explicitly classified as `enabled`, `catalog-only`, or `excluded`;
- the owning domain composes the operation;
- identity, dependency, payload, pagination, redaction, and safety behavior are
  tested where applicable;
- `python3 -m zpa_backup_restore --no-run-ledger coverage --json` remains
  machine-readable and internally consistent; and
- [ZPA_API_COVERAGE_AUDIT.md](ZPA_API_COVERAGE_AUDIT.md) is refreshed with its
  audit date, source counts, and limitations.

Do not enable certificate, private-key, provisioning-key, nonce, privileged
credential, or other secret-bearing operations in generic backup/restore.

## Pull-Request Expectations

A pull request must explain the operator-visible outcome, tenant-write risk,
tests performed, documentation changed, and any live-tenant validation. State
explicitly when validation used only fakes or fixtures. Never include real
credentials, tokens, customer configuration, backups, audit logs, or generated
reports in an issue or pull request.

Use the repository pull-request template as the final review checklist.
