# Managed Recovery Operations

ZPA-Backup and Restore is an independent tool and is not affiliated with or supported by Zscaler. See [../DISCLAIMER.md](../DISCLAIMER.md).

## Local State

The maintained v2 tool separates durable state by purpose:

- `backups/`: authoritative backup, diff, simulation, execution-journal, result, and report artifacts.
- `state/catalog.sqlite3`: searchable snapshot and inventory metadata; it never contains complete resource payloads or credentials.
- `logs/<timestamp>-<command>.log`: detailed, sanitized HTTP request/response audit records.
- `logs/run-ledger.jsonl`: run-level events and artifact hashes.
- `logs/run-ledger.jsonl.head`: the expected ledger event count and head hash, used to expose accidental truncation.

The catalog, ledger, checkpoint, and execution journals are created with owner-only file permissions where the operating system supports them. They still contain sensitive operational metadata and must be protected like the backup directory.

SQLite is used because the catalog needs indexed inventory, history, reference,
and drift queries plus transactional updates and explicit schema migrations.
Python includes the SQLite driver, so this remains a portable single-file local
index without an external database service. Flat JSON remains the authoritative
backup format; losing the catalog loses convenient indexed history, not the
retained backup payloads.

If a real credential is ever pasted into chat, a terminal transcript, source control, an unredacted artifact, or another uncontrolled location, revoke or rotate it immediately and review the relevant tenant/audit history. Deleting the exposed text is not a substitute for rotation.

## Snapshot And Inventory Commands

Generated `backup`, `plan`, and `restore-plan` backups are registered automatically. Existing valid backups can be registered without credentials:

```sh
python3 -m zpa_backup_restore snapshot import backups/older-source.json
python3 -m zpa_backup_restore snapshot list
python3 -m zpa_backup_restore snapshot show latest
python3 -m zpa_backup_restore snapshot verify latest
```

Inventory queries read only the local catalog:

```sh
python3 -m zpa_backup_restore inventory list --snapshot latest
python3 -m zpa_backup_restore inventory search "production app" --snapshot all
python3 -m zpa_backup_restore inventory history \
  --resource-type application_segments --stable-key productionapp
python3 -m zpa_backup_restore inventory references \
  --snapshot latest --resource-type application_segments --stable-key productionapp
python3 -m zpa_backup_restore inventory drift --from <snapshot-id> --to latest
```

List, search, history, references, drift, and snapshot-list output can be exported with `--format json|csv --out <path>`. Snapshot identifiers accept a complete ID, an unambiguous prefix, or `latest`; inventory list/search also accepts `all`.

## Selective Restore

Search the desired snapshot first. `--restore-commands` adds a canonical
selector and copyable `restore-plan` command for every writable match:

```sh
python3 -m zpa_backup_restore inventory search "Access Policy 13" \
  --snapshot latest \
  --resource-type policy_rules \
  --restore-commands
```

The generated command has this form:

```sh
python3 -m zpa_backup_restore restore-plan \
  --source-backup backups/<desired>.json \
  --select 'policy_rules/ACCESS_POLICY:accesspolicy13'
```

Selectors are stable identities:

- ordinary writable objects: `RESOURCE_TYPE/normalized-name`;
- policy rules: `policy_rules/POLICY_TYPE:normalized-name`;
- policy rules may also be entered as
  `policy_rules/POLICY_TYPE/Visible Rule Name`.

Repeat `--select` for several objects. Use `--select-resource RESOURCE_TYPE` to
restore all differences in a writable domain. The `diff`, `plan`, and
`restore-plan` commands accept the same scope flags.

By default the scope changes only the explicitly selected objects. Simulation
still validates all of their references against the Destination backup and
blocks missing mappings. Add `--include-dependencies` to explicitly include
referenced writable dependency objects recursively. Read-only dependencies
cannot be created and continue to block when no unambiguous Destination mapping
exists.

Selective policy restore preserves the Destination policy order by default.
Add `--restore-policy-order` only when the reviewed plan should execute the
bulk reorder operation for the selected policy type. Delete and high-impact
safeguards remain unchanged.

The scope is stored inside the diff and shown in JSON/HTML reports. Preflight
recomputes scoped changes to detect hand-edited omissions. Simulation assurance,
fresh-target drift checks, execution, and residual verification all reuse that
same scope. Unrelated Destination changes do not block or fail a targeted
restore, while drift affecting a selected object still blocks before writes.

## Auditing

Every normal CLI command receives a UUID run ID. The run ledger records application version, command, safeguard selections, result, input/output artifact hashes, and the final detailed HTTP audit-log hash. Sensitive field names and credential-like error text are redacted before persistence.

```sh
python3 -m zpa_backup_restore audit list
python3 -m zpa_backup_restore audit failures
python3 -m zpa_backup_restore audit summary
python3 -m zpa_backup_restore audit show <run-id-or-prefix>
python3 -m zpa_backup_restore audit verify
```

The SHA-256 chain and separate head checkpoint make modification, middle-event removal, reordering, and accidental tail truncation evident. This is tamper-evident, not tamper-proof: a privileged attacker who can replace both files can manufacture a new chain. Copy ledger head hashes to a separately controlled log or archive when stronger evidence is required.

## Assured Restore Procedure

1. Build a restore plan, validate it, and run preflight.
2. Run `simulate` with the exact three restore inputs and intended safeguards.
3. Review both simulation JSON and HTML, including blockers, skips, payloads, methods, paths, and assurance hashes.
4. Pass that exact simulation JSON to live restore.

```sh
python3 -m zpa_backup_restore simulate \
  --source-backup backups/<desired>.json \
  --target-backup backups/<reviewed-target>.json \
  --diff backups/<reviewed-diff>.json \
  --out backups/<reviewed>-simulation.json

python3 -m zpa_backup_restore restore \
  --source-backup backups/<desired>.json \
  --target-backup backups/<reviewed-target>.json \
  --diff backups/<reviewed-diff>.json \
  --simulation backups/<reviewed>-simulation.json \
  --yes
```

The live command validates the simulation and safeguards before loading destination credentials. It then captures a fresh pre-restore destination snapshot. Any configuration change or exact-plan change blocks all writes and requires a new simulation.

During execution, an owner-only JSON journal is atomically updated before and after every operation. After execution, the tool captures another destination snapshot and writes a residual diff and HTML verification report. A non-empty residual diff returns failure even when individual API calls succeeded; expected safety skips must still be reviewed.

`--allow-unreviewed-plan` is an audited compatibility bypass. Use it only for recovery from older automation that cannot yet provide an assured simulation. Deletes and high-impact resources remain separately disabled unless their explicit flags are supplied.

## Production Rehearsal In A Lab Tenant

Complete this rehearsal before approving a release or workflow for production.
Use dedicated non-production source and destination tenants. Never point the
destination credential profile at a production tenant during rehearsal.

### Preparation

1. Give the API credentials only the permissions required for the resources
   under test. Store them in the documented environment variables or masked UI
   fields, never in commands, source files, or review artifacts.
2. Select a representative but bounded configuration set. Include dependency
   chains such as connector group → server group → Application Segment and at
   least one policy rule. Test deletes and high-impact operations in separate,
   explicitly approved runs.
3. Capture and verify a baseline destination backup. Keep an encrypted copy
   outside the working machine so the lab can be returned to its starting
   state.
4. Define acceptance criteria: expected create/update/skip counts, permitted
   high-impact operations, expected residual differences, and an application
   connectivity test.

### Read-Only Planning

Build, validate, and preflight the exact rehearsal set:

```sh
python3 -m zpa_backup_restore plan
python3 -m zpa_backup_restore validate \
  --backup backups/<source>.json \
  --backup backups/<target>.json \
  --diff backups/<diff>.json \
  --strict-manifest
python3 -m zpa_backup_restore preflight \
  --source-backup backups/<source>.json \
  --target-backup backups/<target>.json \
  --diff backups/<diff>.json
python3 -m zpa_backup_restore simulate \
  --source-backup backups/<source>.json \
  --target-backup backups/<target>.json \
  --diff backups/<diff>.json \
  --out backups/<rehearsal>-simulation.json
```

Review both simulation formats. Confirm the destination customer, ordered
methods and paths, sanitized payloads, ID remapping, deferred references,
skipped reasons, blockers, and assurance hashes. A blocked simulation is a
failed rehearsal; do not bypass it.

### Controlled Restore And Verification

Start without `--allow-delete` or `--allow-high-impact`. Add either flag only
when the corresponding operations are part of the written acceptance criteria:

```sh
python3 -m zpa_backup_restore restore \
  --source-backup backups/<source>.json \
  --target-backup backups/<target>.json \
  --diff backups/<diff>.json \
  --simulation backups/<rehearsal>-simulation.json \
  --yes
```

After the command:

1. Require a successful fresh-target drift check and inspect every execution
   journal entry.
2. Review the restore result, post-restore snapshot, residual diff/report, HTTP
   audit log, and run-ledger event. A non-empty unexpected residual is a failed
   rehearsal even when every API request succeeded.
3. Verify the changed objects independently in the ZPA Admin Portal.
4. Test actual lab application access, policy evaluation, PRA behavior, and LSS
   delivery as applicable. API success alone is not operational acceptance.
5. Repeat the backup and inventory queries to confirm stable identities,
   references, and history.

### Recovery Exercise And Evidence

Build a new restore plan from the retained baseline destination backup against
the lab’s current state; validate, preflight, simulate, review, and restore it
through the same guarded workflow. Do not replay the first execution journal.
Confirm that the lab returns to the agreed baseline or record any intentionally
retained difference.

Retain the full recovery set listed below with the application version, coverage
output, test scope, approver, timestamps, observed API deviations, and final
acceptance decision. Redact reports before sharing them outside the approved
operations team.

## Retention And Recovery

- Keep at least one verified backup outside the working machine before testing restore.
- Retain the desired backup, reviewed target backup, diff, simulation, pre/post snapshots, execution journal, result, residual report, HTTP audit log, and corresponding run-ledger events as one recovery set.
- Choose retention based on organizational policy and tenant change rate; a common baseline is 30–90 days locally plus longer encrypted archival copies.
- Do not delete a cataloged backup without also accepting that `snapshot verify` will report the artifact missing. The catalog can be rebuilt by importing retained backups.
- Back up `state/catalog.sqlite3`, but treat backup artifacts—not SQLite—as authoritative.
- Before pruning the run ledger, archive it together with its `.head` checkpoint and record the final head hash in a separately controlled system.
- If an execution journal contains a `running` operation after interruption, do not blindly rerun the original diff. Capture the destination again, inspect the journal and HTTP audit, and build a new reviewed simulation from current state.

Encrypted backup files protect only the backup JSON. Diffs, simulations, journals, reports, SQLite state, and logs are plaintext operational records unless the surrounding storage provides encryption.
