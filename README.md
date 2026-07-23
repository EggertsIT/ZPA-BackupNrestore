# ZPA-Backup and Restore Tool

## Disclaimer

ZPA-Backup and Restore is an independent tool. It is not affiliated with, endorsed by, sponsored by, certified by, or supported by Zscaler, Inc. It is provided "as is", without warranty of any kind, and without any Zscaler support, maintenance, or service-level commitment. Operators are responsible for testing, validating, and approving all use before making changes in any tenant. See [DISCLAIMER.md](DISCLAIMER.md).

CLI and desktop tooling for guarded ZPA configuration backup, inventory, audit,
comparison, simulation, and restore through the Zscaler ZPA API:

- `zpa_policy_tool.py` edits one policy rule safely.
- `zpa_cloner.py` is a backup, diff, report, validate, preflight, and guarded restore workflow for ZPA tenants.

## Version 2

Version 2 keeps the existing workflow and backup format, but moves the maintained implementation into the `zpa_backup_restore` package. Its canonical CLI is:

```sh
python3 -m zpa_backup_restore --help
```

An installed package also exposes `zpa-backup-restore`. The existing `python3 zpa_cloner.py ...` commands remain supported as compatibility entry points.

API coverage uses a hybrid structure under `zpa_backup_restore/resources/`: domain packages keep related behavior together, while every modeled HTTP action has its own small declarative module under `resources/operations/`. This makes endpoint additions and audits easy without duplicating authentication, pagination, logging, diff, mapping, or restore code. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the source tree and extension workflow.

Version 2 also provides a managed local recovery layer: a SQLite snapshot catalog, credential-free inventory/history/reference/drift queries, a tamper-evident run ledger, assured restore plans, fresh-target drift protection, per-operation execution journals, and post-restore residual verification. See [docs/OPERATIONS.md](docs/OPERATIONS.md) for command examples, security boundaries, retention, and recovery guidance.

ZPA-Backup and Restore currently covers the high-value migration path first.
Guarded clone coverage includes:

- Microtenants
- AppProtection custom controls and profiles
- Cloud Browser Isolation banners and profiles
- App Connector and Private Service Edge groups
- Segment groups, application servers, and server groups
- Application Segments, including separately gated move/share operations
- LSS configurations
- PRA portals and consoles
- ZPA policy rules, including deterministic rule reordering

Reference inventory and cross-tenant mapping cover identity providers, SAML and
SCIM attributes, SCIM groups, machine groups, posture profiles, trusted
networks, Cloud Connector groups, version profiles, Zscaler clouds, enrollment
certificate metadata, and Browser Access groups.

Business Continuity settings, Private Cloud sites, and Private Cloud Controller
groups are backed up in sanitized form, but their writes are catalog-only until
secret injection and two-phase association restore are designed and lab-tested.
Live Private Cloud Controllers, Emergency Access users, and Privileged Approvals
are audit-only inventory.

The tool intentionally excludes live connector/service-edge instances,
certificate and private-key material, provisioning keys and nonces, privileged
credentials, and other secrets. See
[ZPA_API_COVERAGE_AUDIT.md](ZPA_API_COVERAGE_AUDIT.md) for the operation-level
coverage boundary and known unsupported API families.

## Documentation

- [Architecture and extension workflow](docs/ARCHITECTURE.md)
- [Managed operations, retention, recovery, and lab rehearsal](docs/OPERATIONS.md)
- [Graphical and CLI process](docs/PROCESS.md)
- [ZPA API coverage audit](ZPA_API_COVERAGE_AUDIT.md)
- [Contribution and pull-request workflow](CONTRIBUTING.md)
- [Versioning and release checklist](docs/RELEASE.md)

Credentials are never read from source code. The separate single-rule editor
uses the `ZSCALER_*` profile:

```sh
export ZSCALER_CLIENT_ID="..."
export ZSCALER_CLIENT_SECRET="..."
export ZSCALER_CUSTOMER_ID="..."
export ZSCALER_AUTH_MODE="legacy"
export ZSCALER_ZPA_BASE_URL="https://config.private.zscaler.com"
```

## Main Backup And Restore Workflow

Set source and target tenant credentials:

```sh
export ZPA_SOURCE_AUTH_MODE="legacy"
export ZPA_SOURCE_CLIENT_ID="..."
export ZPA_SOURCE_CLIENT_SECRET="..."
export ZPA_SOURCE_CUSTOMER_ID="..."
export ZPA_SOURCE_ZPA_BASE_URL="https://config.private.zscaler.com"

export ZPA_TARGET_AUTH_MODE="legacy"
export ZPA_TARGET_CLIENT_ID="..."
export ZPA_TARGET_CLIENT_SECRET="..."
export ZPA_TARGET_CUSTOMER_ID="..."
export ZPA_TARGET_ZPA_BASE_URL="https://config.private.zscaler.com"
```

The Source profile is passed only to read-only backup calls. Create, update, and delete operations are constructed only with the Destination profile and only during confirmed live restore/apply. A Source tenant can therefore become a write target only if its credentials/customer ID are mistakenly entered as the Destination profile; verify the destination customer before approving restore.

Launch the desktop UI:

```sh
python3 zpa_cloner_app.py
```

The UI invokes the legacy `zpa_cloner.py` compatibility entry point, which
delegates to the maintained package, and streams command output into the
Activity panel. It includes source and destination tenant credential tabs so an
operator can paste the API mode, client ID, client secret, customer ID, and
legacy ZPA API URL directly into the app. The Workflow panel is ordered as
create/compare backups, restore destination, then review. Policy rule types are
selected with checkboxes; all modeled non-policy ZPA objects are backed up
separately from those rule-type checkboxes. Secrets are masked and are passed
only to the running command process.

The left pane does not require vertical scrolling. Its controls are grouped into
`Workflow`, `Tenants`, `Options`, `Scope`, `Artifacts`, and `Status` tabs. The
Scope tab selects individual objects or complete writable resource types for a
targeted recovery; the Activity log on the right remains independently
scrollable.

The UI can also auto-load an ignored local `.env` file from this directory into the UI process if present; secret values are not displayed.

CLI commands default to clean operator logs with run banners, per-resource backup counts, warning summaries, restore safeguards, and final restore totals. Add `--log-level verbose` before the command name when you need lower-level endpoint diagnostics.

Each backup/restore workflow also writes an ignored HTTP audit log under `logs/<timestamp>-<command>.log` and prints `api:` progress lines while requests are in flight. The audit log is JSON lines and records each API call with method, URL, query parameters, sanitized request headers, sanitized request body, response status, duration, sanitized response headers, response bytes, response shape, record counts, and sanitized response body. It redacts bearer tokens, authorization headers, cookies, client secrets, passwords, private keys, tokens, certificates, and known credential fields. Because it contains tenant configuration details, treat audit logs as sensitive operational records. Use `--audit-log <path>` to choose the file and `--no-api-progress` to keep the screen output quieter while still writing the audit file.

A separate `logs/run-ledger.jsonl` correlates commands, safeguards, results, and artifact SHA-256 hashes under a UUID run ID. Its event hash chain and `.head` checkpoint are tamper-evident, not tamper-proof. Inspect it with `audit list|show|summary|failures|verify`.

Encrypted backups can be written with OpenSSL-compatible `.json.enc` files:

```sh
export ZPA_BACKUP_PASSPHRASE="use-a-long-unique-passphrase"
python3 zpa_cloner.py --encrypt-backups plan
```

This encrypts source and destination backup JSON files. Diffs, HTML reports,
simulations, restore results, catalog data, journals, and audit logs remain
normal files and must be protected separately. Commands that read backups,
including `validate`, `diff`, `preflight`, `simulate`, `report`,
`restore-plan`, and `restore`, can read `.json.enc` files when
`ZPA_BACKUP_PASSPHRASE` is set. The desktop UI exposes the same behavior in the
Backup Security panel with `Encrypt backup files` and a masked passphrase field.

Backups are encrypted with OpenSSL `enc`, `aes-256-cbc`, PBKDF2, 200000 iterations, and SHA-256 so they can be decrypted without this tool:

```sh
export ZPA_BACKUP_PASSPHRASE="use-a-long-unique-passphrase"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -in backups/<timestamp>-source.json.enc \
  -out backups/<timestamp>-source.json \
  -pass env:ZPA_BACKUP_PASSPHRASE
```

Use `--backup-passphrase-env <NAME>` to read the passphrase from another environment variable and `--openssl-bin <path>` when the OpenSSL executable is not on `PATH`. Run `validate --strict-manifest` after decryption or before restore to verify the backup manifest checksum.

Application Segment backup uses the paginated `GET /application` response directly because that endpoint returns detailed application segment records. This avoids one extra `GET /application/{id}` call per application segment while still using `pagesize=500` pagination for larger tenants.

For a graphical end-to-end process description covering backup, compare, restore from past snapshots, validation, preflight, safeguards, and tenant write boundaries, see [docs/PROCESS.md](docs/PROCESS.md).

Build a macOS app bundle:

```sh
python3 build_macos_app.py
```

This writes `dist/ZPA-Backup and Restore.app`. When launched as an app, runtime files such as `.env`, backups, diffs, restore results, and reports are read and written under `~/Documents/ZPA-Backup and Restore`. Credentials entered in the UI are kept in memory for that app session unless you separately place them in `.env`.

On Apple Silicon Macs, the app launcher skips Intel-only Python binaries and shell shims so it does not trigger Rosetta just because an old `/usr/local/bin/python3` exists. Install a native arm64 Python 3 with Tkinter, for example through Homebrew in `/opt/homebrew` or the official python.org universal installer. If you override the Python path with `ZPA_BACKUP_RESTORE_PYTHON`, point it at the real native Python binary, not a pyenv/asdf/conda shim.

Back up both tenants and produce a diff without changing anything:

```sh
python3 zpa_cloner.py plan
```

This writes:

- `backups/<timestamp>-source.json`
- `backups/<timestamp>-target.json`
- `backups/<timestamp>-diff.json`
- `backups/<timestamp>-diff.html`

Each backup includes a manifest with schema version, resource counts, endpoint error count, and a SHA-256 checksum over the backup contents.

In the UI, use:

- `Backup Source` or `Backup Destination` to capture a point-in-time snapshot.
- `Compare Source to Destination` to back up both live tenants and create a diff/report.
- `Choose Desired Backup` to select an older snapshot.
- `Build Restore Plan` to back up current destination and generate the restore diff/report.
- `Validate`, `Preflight`, `Simulate`, and `Restore` in that order before writing.

Restore destination from an older backup snapshot:

```sh
python3 zpa_cloner.py restore-plan \
  --source-backup backups/<older-source-or-desired-state>.json
```

This does not write changes. It uses the selected backup as the desired state, takes a fresh backup of the current destination tenant, creates a restore diff, and writes a report. Then run `preflight`, `simulate`, and finally `restore --simulation <reviewed-simulation.json> --yes` from the generated files.

The policy rule types in the selected backup are used for the fresh destination backup when the backup contains manifest metadata. This keeps the restore comparison scoped to the rule types that actually existed in that snapshot.

### Selective Restore

Inventory can print the canonical selector and exact first command for a
writable object:

```sh
python3 -m zpa_backup_restore inventory search "Access Policy 13" \
  --snapshot latest \
  --resource-type policy_rules \
  --restore-commands
```

For example, restore only that historical Access Policy rule:

```sh
python3 -m zpa_backup_restore restore-plan \
  --source-backup backups/<desired-snapshot>.json \
  --select 'policy_rules/ACCESS_POLICY:accesspolicy13'
```

`restore-plan` captures the current Destination tenant and writes a scoped diff
and HTML report. Its output prints the exact `simulate` command; `simulate`
prints the exact reviewed `restore` command. Repeat `--select` to restore
several objects, or select a complete writable domain:

```sh
python3 -m zpa_backup_restore restore-plan \
  --source-backup backups/<desired-snapshot>.json \
  --select-resource application_segments
```

Selection uses stable resource type/name identity rather than source or
destination object IDs. Invalid, missing, or ambiguous selectors block
planning. Referenced writable dependencies are validated but never added
implicitly; pass `--include-dependencies` only when the plan should recursively
include them. Policy bulk reorder is excluded from selective policy restore
unless `--restore-policy-order` is explicitly supplied.

The selected scope is persisted in the diff and bound into simulation hashes,
fresh-destination drift protection, the execution journal, and post-restore
verification. Unrelated differences elsewhere in the tenant are not written
and do not make a successful targeted recovery appear to fail. Do not edit a
scoped diff by hand; preflight recomputes it from the desired backup, reviewed
target, and persisted scope.

Limit policy rule types only when you intentionally want a narrower rule backup:

```sh
python3 zpa_cloner.py \
  --policy-type ACCESS_POLICY \
  --policy-type TIMEOUT_POLICY \
  --policy-type INSPECTION_POLICY \
  plan
```

Validate the generated files before restore:

```sh
python3 zpa_cloner.py validate \
  --backup backups/<timestamp>-source.json \
  --backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json \
  --strict-manifest
```

Run restore preflight:

```sh
python3 zpa_cloner.py preflight \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json
```

Restore only after reviewing the generated backup, diff, preflight, simulation JSON, and simulation HTML report:

```sh
python3 zpa_cloner.py restore \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json \
  --simulation backups/<timestamp>-simulation.json \
  --yes
```

Live restore requires the reviewed simulation by default. Before any write it captures a fresh destination backup and blocks if the destination state or recomputed operation plan has changed. It then writes an atomic per-operation execution journal, captures a post-restore destination backup, and produces a residual diff/report. Residual differences make the run unsuccessful instead of being silently described as complete.

Deletes are skipped by default. Add `--allow-delete` only when you want the restore to remove target objects missing from source.

Microtenant writes and Application Segment move/share operations are also
skipped by default because they are high-impact. Add `--allow-high-impact` only
after reviewing the simulation and confirming those operations are intended.

Build a credential-free restore simulation from existing files:

```sh
python3 -m zpa_backup_restore simulate \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json
```

Simulation is completely offline: it does not require source or destination credentials and does not make HTTP calls. It writes `backups/<timestamp>-simulation.json` and a matching HTML report containing the ordered HTTP methods and destination paths, sanitized final payloads, safety skips grouped by reason, deferred IDs from earlier planned creates, and blocking unresolved references. A blocked simulation exits unsuccessfully after writing the artifacts so automation cannot mistake it for a safe plan.

The JSON also binds the source backup, reviewed target backup, diff, normalized target state, safeguard selections, and exact ordered plan with deterministic SHA-256 values. Use the same flags for simulation and restore.

`restore --dry-run` and `apply --dry-run` remain compatibility aliases for `simulate`.

`apply` remains available as an alias for restore-oriented automation, but `restore` is the recommended operator command.

Manage historical backups and query inventory without tenant credentials:

```sh
python3 -m zpa_backup_restore snapshot import backups/<older>.json
python3 -m zpa_backup_restore snapshot list
python3 -m zpa_backup_restore inventory search "app name" --snapshot all --restore-commands
python3 -m zpa_backup_restore inventory drift --from <snapshot-id> --to latest
python3 -m zpa_backup_restore audit verify
```

Generate or regenerate an HTML report:

```sh
python3 zpa_cloner.py report \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json \
  --out backups/<timestamp>-report.html
```

Show current resource coverage:

```sh
python3 zpa_cloner.py coverage
```

For current official-doc coverage status, see [ZPA_API_COVERAGE_AUDIT.md](ZPA_API_COVERAGE_AUDIT.md).

The operating model is: back up source and destination, compute a name-based
diff, validate manifests, preflight the restore set, simulate sanitized ordered
requests with ID remapping, and restore to the destination in dependency order.

Endpoint declarations are audited against the
[official ZPA API reference](https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa)
and its sitemap. The dated results, classifications, and limitations are kept
in [ZPA_API_COVERAGE_AUDIT.md](ZPA_API_COVERAGE_AUDIT.md).

## Single Rule Edit

Find the target rule first:

```sh
python3 zpa_policy_tool.py list-rules --policy-type ACCESS_POLICY --search "<rule name>"
```

Dry-run adding an AzureAD SCIM Username criterion:

```sh
python3 zpa_policy_tool.py add-scim-criteria \
  --policy-set-id "<policy-set-id>" \
  --rule-id "<rule-id>" \
  --idp-name "AzureAD" \
  --attribute-name "Username" \
  --value "user@example.com"
```

If the diff is correct, apply it:

```sh
python3 zpa_policy_tool.py add-scim-criteria \
  --policy-set-id "<policy-set-id>" \
  --rule-id "<rule-id>" \
  --idp-name "AzureAD" \
  --attribute-name "Username" \
  --value "user@example.com" \
  --apply
```

By default, the command:

- Resolves the access policy set ID from `ACCESS_POLICY`.
- Resolves the IdP by name.
- Resolves the SCIM attribute by name, with `Username` matching `userName`.
- Fetches the current rule.
- Adds the criterion as a dry-run diff unless `--apply` is passed.
- Merges another value into an existing matching SCIM attribute condition when possible, preserving OR semantics.
- Writes original and modified rule JSON under `backups/` before applying.

Useful inspection commands:

```sh
python3 zpa_policy_tool.py list-idps
python3 zpa_policy_tool.py list-scim-attributes --idp-name "AzureAD"
python3 zpa_policy_tool.py list-scim-values --idp-name "AzureAD" --attribute-name "Username"
python3 zpa_policy_tool.py get-rule --rule-id "<rule-id>"
```

ZPA policy updates are made with the ZPA policy rule update endpoint. If your tenant workflow still requires an admin-side publish/activation step, complete that in the ZPA Admin Portal after applying.
