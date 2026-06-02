# ZPA-Backup and Restore Tool

Small CLI and desktop tooling for ZPA policy backup and restore work through the Zscaler ZPA API:

- `zpa_policy_tool.py` edits one policy rule safely.
- `zpa_cloner.py` is a backup, diff, report, validate, preflight, and guarded restore workflow for ZPA tenants.

ZPA-Backup and Restore currently covers the high-value migration path first:

- Microtenants
- Inspection Custom Controls
- Inspection Profiles
- Cloud Browser Isolation Profiles
- App Connector Groups
- Service Edge Groups
- Segment Groups
- Servers
- Server Groups
- Application Segments
- LSS Configurations
- PRA Portals
- PRA Consoles
- ZPA policy rules, defaulting to all supported policy rule types
- IdP, SCIM attribute, and SCIM group references for ID remapping
- Read-only inventory for CBI banners, machine groups, posture profiles, and trusted networks

It intentionally does not clone live connector/service-edge instances, certificates, provisioning keys, privileged credentials, or secrets.

The tool keeps credentials out of source code. Set these environment variables before running it:

```sh
export ZSCALER_CLIENT_ID="..."
export ZSCALER_CLIENT_SECRET="..."
export ZSCALER_CUSTOMER_ID="..."
export ZSCALER_AUTH_MODE="legacy"
export ZSCALER_ZPA_BASE_URL="https://config.private.zscaler.com"
```

## ZPA-Backup and Restore

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

Launch the desktop UI:

```sh
python3 zpa_cloner_app.py
```

The UI wraps the same `zpa_cloner.py` commands and streams their output into the Activity panel while they run. It includes source and destination tenant credential tabs so an operator can paste the API mode, client ID, client secret, customer ID, and legacy ZPA API URL directly into the app. The Workflow panel is ordered as create/compare backups, restore destination, then review. Policy rule types are selected with checkboxes; all modeled non-policy ZPA objects are backed up separately from those rule-type checkboxes. Secrets are masked and are passed only to the running command process.

The UI can also auto-load an ignored local `.env` file from this directory into the UI process if present; secret values are not displayed.

For a graphical end-to-end process description covering backup, compare, restore from past snapshots, validation, preflight, safeguards, and tenant write boundaries, see [docs/PROCESS.md](docs/PROCESS.md).

Build a macOS app bundle:

```sh
python3 build_macos_app.py
```

This writes `dist/ZPA-Backup and Restore.app`. When launched as an app, runtime files such as `.env`, backups, diffs, restore results, and reports are read and written under `~/Documents/ZPA-Backup and Restore`. Credentials entered in the UI are kept in memory for that app session unless you separately place them in `.env`.

On Apple Silicon Macs, the app launcher skips Intel-only Python binaries so it does not trigger Rosetta just because an old `/usr/local/bin/python3` exists. Install a native arm64 Python 3 with Tkinter, for example through Homebrew in `/opt/homebrew` or the official python.org universal installer.

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
- `Validate`, `Preflight`, `Dry Run`, and `Restore` in that order before writing.

Restore destination from an older backup snapshot:

```sh
python3 zpa_cloner.py restore-plan \
  --source-backup backups/<older-source-or-desired-state>.json
```

This does not write changes. It uses the selected backup as the desired state, takes a fresh backup of the current destination tenant, creates a restore diff, and writes a report. Then run `preflight`, `restore --dry-run`, and finally `restore --yes` from the generated files.

The policy rule types in the selected backup are used for the fresh destination backup when the backup contains manifest metadata. This keeps the restore comparison scoped to the rule types that actually existed in that snapshot.

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

Restore only after reviewing the generated backup, diff, preflight, and HTML report:

```sh
python3 zpa_cloner.py restore \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json \
  --yes
```

Deletes are skipped by default. Add `--allow-delete` only when you want the restore to remove target objects missing from source.

Microtenant writes are also skipped by default because they are high-impact tenant partitioning changes. Add `--allow-high-impact` only after reviewing the report.

Run a write-path simulation from existing files:

```sh
python3 zpa_cloner.py restore \
  --source-backup backups/<timestamp>-source.json \
  --target-backup backups/<timestamp>-target.json \
  --diff backups/<timestamp>-diff.json \
  --dry-run
```

`apply` remains available as an alias for restore-oriented automation, but `restore` is the recommended operator command.

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

The tool follows the same operating model as ZIA-Cloner: backup source and target, compute a name-based diff, validate manifests, preflight the restore set, remap IDs from source to target, dry-run/report, then restore in dependency order.

Official Zscaler Automation Hub ZPA API reference pages used for the initial resource coverage:

- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/application-segment-management/gets-all-configured-application-segments-for-the-specified-customer
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/segment-group-management/gets-all-configured-segment-groups-for-the-specified-customer
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/server-group-management/gets-all-configured-server-groups-for-the-specified-customer
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/app-connector-group-management/gets-all-configured-app-connector-groups-for-the-specified-customer
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/policy-management/gets-paginated-policy-rules-for-the-specified-policy-type
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/scim-attributes/gets-all-scim-attributes-for-the-specified-id
- https://automate.zscaler.com/docs/api-reference-and-guides/api-reference/zpa/scim-groups/get-all-scim-groups

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

For a known rule and policy set ID, use:

```sh
python3 zpa_policy_tool.py add-scim-criteria \
  --policy-set-id "<policy-set-id>" \
  --rule-id "<rule-id>" \
  --idp-name "AzureAD" \
  --attribute-name "Username" \
  --value "user@example.com"
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
