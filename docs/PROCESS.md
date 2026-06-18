# ZPA-Backup and Restore Process

ZPA-Backup and Restore is an independent tool. It is not affiliated with, endorsed by, sponsored by, certified by, or supported by Zscaler, Inc. It is provided "as is", without warranty of any kind. See [../DISCLAIMER.md](../DISCLAIMER.md).

This page describes how the tool operates, which actions read or write a tenant, and how backup, restore, validation, and reporting fit together.

## Feature Map

```mermaid
flowchart LR
    UI[Desktop UI<br/>zpa_cloner_app.py] --> CLI[zpa_cloner.py]
    AppBundle[macOS app bundle<br/>build_macos_app.py] --> UI

    CLI --> Backup[Backup]
    CLI --> Compare[Compare / Plan]
    CLI --> RestorePlan[Restore Plan]
    CLI --> Validate[Validate]
    CLI --> Preflight[Preflight]
    CLI --> DryRun[Dry Run]
    CLI --> Restore[Restore]
    CLI --> Report[HTML Report]
    CLI --> Coverage[Coverage]
    CLI --> Encryption[Optional backup encryption]

    SingleRule[zpa_policy_tool.py<br/>single rule edit] --> DirectPolicyWrite[Direct policy rule update]

    Backup --> SourceBackup[(source backup JSON<br/>or .json.enc)]
    Backup --> DestinationBackup[(destination backup JSON<br/>or .json.enc)]
    Compare --> Diff[(diff JSON)]
    Compare --> CompareReport[(diff HTML)]
    RestorePlan --> RestoreDiff[(restore diff JSON)]
    RestorePlan --> RestoreReport[(restore plan HTML)]
    DryRun --> DryRunResult[(dry-run result JSON/HTML)]
    Restore --> RestoreResult[(restore result JSON/HTML)]
    Encryption --> OpenSSL[OpenSSL-compatible<br/>external decryption]
```

## Tenant Safety Boundary

```mermaid
flowchart LR
    SourceTenant[Source tenant] -- read only backup API calls --> Tool[ZPA-Backup and Restore]
    DestinationTenant[Destination tenant] -- read backup API calls --> Tool
    Tool -- create/update/delete only during restore/apply --> DestinationTenant

    DesiredBackup[(older or source backup)] -- local file read --> Tool
    Tool -- backup/diff/report/result files --> LocalFiles[(local backups folder)]

    Warning{Source credentials entered<br/>as Destination?}
    Warning --> Impact[That tenant becomes the write target]
```

In the normal source-to-destination workflow, Source is only read. The only way Source can be modified by the restore workflow is if the operator intentionally or accidentally enters Source credentials in the Destination tab or target environment variables.

## Main UI Workflow

```mermaid
flowchart TD
    Start[Open desktop UI] --> Credentials[Enter Source and Destination credentials]
    Credentials --> BackupSecurity[Optional Backup Security<br/>encrypt backups and enter passphrase]
    BackupSecurity --> Scope[Choose policy rule type checkboxes]

    Scope --> BackupSource[Backup Source]
    Scope --> BackupDestination[Backup Destination]
    Scope --> Compare[Compare Source to Destination]

    BackupSource --> SourceFile[(source backup JSON<br/>or .json.enc)]
    BackupDestination --> DestinationFile[(destination backup JSON<br/>or .json.enc)]
    Compare --> SourceFile
    Compare --> DestinationFile
    Compare --> DiffFile[(diff JSON)]
    Compare --> ReportFile[(HTML report)]

    SourceFile --> Choose[Choose Desired Backup]
    Choose --> RestorePlan[Build Restore Plan]
    RestorePlan --> CurrentDestination[(fresh destination backup<br/>or .json.enc)]
    RestorePlan --> RestoreDiff[(restore diff JSON)]
    RestorePlan --> RestoreReport[(restore plan HTML)]

    RestoreDiff --> Validate[Validate]
    Validate --> Preflight[Preflight]
    Preflight --> DryRun[Dry Run]
    DryRun --> Review[Review activity log and HTML report]
    Review --> Restore[Restore]
    Restore --> RestoreResult[(restore result JSON/HTML)]
```

When backup encryption is enabled, source and destination backup files use `.json.enc` instead of `.json`. The passphrase is entered in the masked Backup Security field or supplied through the configured environment variable.

## Backup And Compare

```mermaid
sequenceDiagram
    participant Operator
    participant Tool
    participant Source as Source Tenant
    participant Dest as Destination Tenant
    participant Files as Local Files

    Operator->>Tool: Compare Source to Destination
    Tool->>Source: GET modeled resources
    Source-->>Tool: Source configuration
    Tool->>Dest: GET modeled resources
    Dest-->>Tool: Destination configuration
    Tool->>Tool: Normalize objects and remove tenant-specific IDs
    Tool->>Tool: Match resources by type and name
    Tool->>Files: Write source backup, destination backup, diff, report
    opt Backup encryption enabled
        Tool->>Files: Store source and destination backups as .json.enc
    end
    Tool-->>Operator: Activity log, artifact paths, summary counts
```

Backup and compare do not write to either tenant.

## Encrypted Backup Storage

```mermaid
flowchart TD
    Enable[Operator enables encrypted backups] --> Passphrase[Passphrase from masked UI field<br/>or environment variable]
    Passphrase --> OpenSSL[OpenSSL enc<br/>aes-256-cbc + PBKDF2]
    OpenSSL --> EncryptedBackup[(backup.json.enc)]

    EncryptedBackup --> ToolRead[Tool reads encrypted backup]
    ToolRead --> Validate[Validate manifest checksum]
    EncryptedBackup --> External[External OpenSSL decrypt]
    External --> PlainBackup[(backup.json)]

    Diff[(diff JSON)] --> PlainArtifacts[Plaintext artifacts]
    Report[(HTML report)] --> PlainArtifacts
    Audit[(audit log)] --> PlainArtifacts
```

Encrypted backups are designed to be portable. They can be decrypted without this tool by setting the passphrase environment variable and running OpenSSL:

```sh
export ZPA_BACKUP_PASSPHRASE="..."
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
  -in backups/<timestamp>-source.json.enc \
  -out backups/<timestamp>-source.json \
  -pass env:ZPA_BACKUP_PASSPHRASE
```

Only backup JSON files are encrypted by `--encrypt-backups`. Diff JSON, HTML reports, restore result files, and HTTP audit logs remain plaintext and must be protected separately.

## Restore From A Past Snapshot

```mermaid
sequenceDiagram
    participant Operator
    participant Tool
    participant Dest as Destination Tenant
    participant Files as Local Files

    Operator->>Tool: Choose Desired Backup
    Tool->>Files: Read selected backup JSON or JSON.enc
    Operator->>Tool: Build Restore Plan
    Tool->>Dest: GET current destination resources
    Dest-->>Tool: Current destination configuration
    Tool->>Tool: Compute desired state vs current destination
    Tool->>Files: Write restore-target backup, restore diff, restore plan report
    opt Backup encryption enabled
        Tool->>Files: Store fresh destination backup as .json.enc
    end
    Operator->>Tool: Validate
    Tool->>Files: Validate backup manifests, checksums, and diff structure
    Operator->>Tool: Preflight
    Tool->>Tool: Check dependency order, missing references, backup errors, customer mismatch
    Operator->>Tool: Dry Run
    Tool->>Tool: Simulate create/update/delete order without API writes
    Operator->>Tool: Restore
    Tool->>Dest: POST/PUT/DELETE in dependency order
    Dest-->>Tool: Write results
    Tool->>Files: Write restore result and restore report
```

Restore from a past snapshot does not require live Source tenant access. It uses the chosen backup file as the desired state and writes only to the configured Destination tenant.

## Validation And Preflight Gates

```mermaid
flowchart TD
    Files[(backup and diff files)] --> Encrypted{Backup file is .json.enc?}
    Encrypted -- yes --> Decrypt[Decrypt with passphrase]
    Decrypt --> Validate
    Encrypted -- no --> Validate
    Validate --> Manifest{Manifest present<br/>and checksum valid?}
    Manifest -- no --> BlockValidate[Validation fails]
    Manifest -- yes --> DiffShape{Diff structure valid?}
    DiffShape -- no --> BlockValidate
    DiffShape -- yes --> Preflight[Preflight]

    Preflight --> Customer{Source and Destination<br/>customer IDs make sense?}
    Customer -- no --> BlockPreflight[Preflight blocks restore]
    Customer -- yes --> Errors{Endpoint errors<br/>in backups?}
    Errors -- yes --> AllowFailed{Allow failed backups?}
    AllowFailed -- no --> BlockPreflight
    AllowFailed -- yes --> Dependency
    Errors -- no --> Dependency{Dependency order valid?}
    Dependency -- no --> BlockPreflight
    Dependency -- yes --> References{Required references resolvable?}
    References -- no --> BlockPreflight
    References -- yes --> DryRun[Dry Run allowed]

    DryRun --> Restore{Operator confirms Restore?}
    Restore -- no --> Stop[No tenant changes]
    Restore -- yes --> Apply[Write to Destination]
```

Validate decrypts encrypted backups before checking file integrity and structure. Preflight checks whether the restore set is safe and internally consistent before write operations are allowed.

## Restore Write Order

```mermaid
flowchart TD
    Start[Restore starts] --> Creates[Create missing writable resources]
    Creates --> Updates[Update changed writable resources]
    Updates --> Deletes{Deletes allowed?}
    Deletes -- no --> SkipDeletes[Skip delete actions]
    Deletes -- yes --> DeleteDependents[Delete dependents first]
    DeleteDependents --> DeleteDependencies[Delete dependencies last]
    SkipDeletes --> Result[Write result and report]
    DeleteDependencies --> Result
```

Creates and updates follow the declared migration order so dependencies exist before dependent resources are written. Deletes run in reverse order so dependents are removed before dependencies.

## Resource Scope

```mermaid
flowchart LR
    Scope[Backup scope] --> NonPolicy[Modeled non-policy resources<br/>always included]
    Scope --> PolicyRules[Policy rule resources<br/>controlled by checkboxes]

    NonPolicy --> AppSegments[Application segments]
    NonPolicy --> SegmentGroups[Segment groups]
    NonPolicy --> ServerGroups[Server groups]
    NonPolicy --> Servers[Servers]
    NonPolicy --> Connectors[Connector and service edge groups]
    NonPolicy --> Inspection[Inspection and CBI profiles]
    NonPolicy --> PRA[PRA portals and consoles]
    NonPolicy --> LSS[LSS configs]
    NonPolicy --> Inventory[Read-only reference inventory]

    PolicyRules --> Access[Access]
    PolicyRules --> Timeout[Timeout]
    PolicyRules --> InspectionPolicy[Inspection]
    PolicyRules --> OtherPolicies[Other supported rule types]
```

The policy checkboxes affect policy rule types only. They do not exclude application segments, server groups, segment groups, or other modeled non-policy resources.

## Safeguards

```mermaid
flowchart TD
    RestoreAction[Restore action] --> Confirm[Explicit operator confirmation]
    Confirm --> YesFlag[CLI requires --yes for writes]
    YesFlag --> DeleteFlag{--allow-delete?}
    DeleteFlag -- no --> NoDelete[Deletes skipped]
    DeleteFlag -- yes --> DeleteAllowed[Deletes can run]
    YesFlag --> HighImpactFlag{--allow-high-impact?}
    HighImpactFlag -- no --> HighImpactSkipped[Microtenant writes skipped]
    HighImpactFlag -- yes --> HighImpactAllowed[High-impact writes can run]
    YesFlag --> PreflightGate{Preflight passes?}
    PreflightGate -- no --> Block[Restore blocked]
    PreflightGate -- yes --> WriteTarget[Write to Destination tenant]
```

Default behavior is conservative: no writes without explicit confirmation, deletes skipped unless enabled, and high-impact microtenant writes skipped unless enabled.

## Artifact Lifecycle

```mermaid
flowchart TD
    LiveSource[Live Source] --> SourceBackup[(timestamp-source.json<br/>or .json.enc)]
    LiveDestination[Live Destination] --> TargetBackup[(timestamp-target.json<br/>or .json.enc)]
    SourceBackup --> Diff[(timestamp-diff.json)]
    TargetBackup --> Diff
    Diff --> DiffReport[(timestamp-diff.html)]

    DesiredBackup[(older desired backup)] --> RestorePlan[restore-plan]
    LiveDestination --> RestoreTarget[(timestamp-restore-target.json<br/>or .json.enc)]
    RestoreTarget --> RestoreDiff[(timestamp-restore-diff.json)]
    DesiredBackup --> RestoreDiff
    RestoreDiff --> RestorePlanReport[(timestamp-restore-diff.html)]
    RestoreDiff --> DryRunResult[(timestamp-restore-result.json/html dry-run)]
    RestoreDiff --> RestoreResult[(timestamp-restore-result.json/html)]
```

Every significant operation writes local artifacts so an operator can review what happened and rerun validation/reporting from files.

## Single Rule Edit

```mermaid
flowchart TD
    Start[Single rule edit CLI] --> ListRules[list-rules]
    ListRules --> ReviewRule[Review target rule ID]
    ReviewRule --> DryRun[add-scim-criteria default dry-run]
    DryRun --> Diff[Show before/after payload]
    Diff --> Apply{Operator passes --apply?}
    Apply -- no --> NoChange[No tenant change]
    Apply -- yes --> WriteRule[PUT policy rule to configured tenant]
```

The single-rule tool is separate from backup/restore. It writes only when `--apply` is passed and uses the single-tenant `ZSCALER_*` credential set.

## Command Summary

| Feature | UI action | CLI command | Tenant write risk |
| --- | --- | --- | --- |
| Backup Source | `Backup Source` | `zpa_cloner.py backup source` | None |
| Backup Destination | `Backup Destination` | `zpa_cloner.py backup target` | None |
| Compare tenants | `Compare Source to Destination` | `zpa_cloner.py plan` | None |
| Restore from snapshot | `Build Restore Plan` | `zpa_cloner.py restore-plan` | None |
| Validate files | `Validate` | `zpa_cloner.py validate` | None |
| Preflight restore | `Preflight` | `zpa_cloner.py preflight` | None |
| Simulate restore | `Dry Run` | `zpa_cloner.py restore --dry-run` | None |
| Apply restore | `Restore` | `zpa_cloner.py restore --yes` | Destination only |
| Generate report | `Report` | `zpa_cloner.py report` | None |
| Show coverage | `Coverage` | `zpa_cloner.py coverage` | None |
| Edit one rule | Not part of main UI | `zpa_policy_tool.py add-scim-criteria --apply` | Configured single tenant |
