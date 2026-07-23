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
    CLI --> Simulation[Offline Simulation]
    CLI --> Restore[Restore]
    CLI --> Report[HTML Report]
    CLI --> Coverage[Coverage]
    CLI --> Encryption[Optional backup encryption]
    CLI --> SnapshotCatalog[Snapshot / Inventory]
    CLI --> RunAudit[Run Audit]
    CLI --> DR[Disaster Recovery Runbook]

    SingleRule[zpa_policy_tool.py<br/>single rule edit] --> DirectPolicyWrite[Direct policy rule update]

    Backup --> SourceBackup[(source backup JSON<br/>or .json.enc)]
    Backup --> DestinationBackup[(destination backup JSON<br/>or .json.enc)]
    Compare --> Diff[(diff JSON)]
    Compare --> CompareReport[(diff HTML)]
    RestorePlan --> RestoreDiff[(restore diff JSON)]
    RestorePlan --> RestoreReport[(restore plan HTML)]
    Simulation --> SimulationResult[(simulation JSON/HTML)]
    Restore --> RestoreResult[(restore result JSON/HTML)]
    SnapshotCatalog --> Catalog[(state/catalog.sqlite3)]
    RunAudit --> Ledger[(hash-chained run ledger)]
    DR --> DRJson[(auditable DR runbook JSON)]
    DR --> DRHtml[(printable setting checklist HTML)]
    Restore --> RestoreChecks[(pre/post snapshots<br/>journal + residual report)]
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

The fixed left pane uses six focused tabs: `Workflow` for ordered actions,
`Tenants` for source/destination credentials, `Options` for backup policy scope
and safeguards, `Scope` for selective restore, `Artifacts` for generated or
selected files, and `Status` for environment readiness. Each tab fits at the
minimum supported window size without vertical scrolling. Command output
scrolls independently in the right-side Activity panel.

Hover over a tab, action, field, artifact, or safeguard to see a short
explanation. The same explanations appear when a supported control receives
keyboard focus. Tooltips clarify behavior and safety impact; every core action
remains available through a visible, self-contained label.

After selecting a Desired backup, `DR Runbook` creates the canonical JSON and
printable HTML checklist without tenant credentials. `Open DR Checklist` opens
the generated guide. The Workflow tab keeps the DR action in its existing
Review row, so the left panel remains non-scrolling.

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
    Choose --> RestoreScope{Complete or selective<br/>restore scope?}
    RestoreScope --> RestorePlan[Build Restore Plan]
    RestorePlan --> CurrentDestination[(fresh destination backup<br/>or .json.enc)]
    RestorePlan --> RestoreDiff[(restore diff JSON)]
    RestorePlan --> RestoreReport[(restore plan HTML)]

    RestoreDiff --> Validate[Validate]
    Validate --> Preflight[Preflight]
    Preflight --> Simulation[Simulate]
    Simulation --> Review[Review ordered requests,<br/>payloads, skips, and blockers]
    Review --> Assured[Select reviewed simulation]
    Assured --> Restore[Restore]
    Restore --> FreshCheck[Fresh destination snapshot<br/>and drift gate]
    FreshCheck --> RestoreResult[(journal + restore result)]
    RestoreResult --> VerifyResult[(post snapshot + residual report)]
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
    Operator->>Tool: Simulate
    Tool->>Tool: Build ordered methods, paths, sanitized payloads, and reference diagnostics
    Tool->>Files: Write assured simulation JSON and HTML
    Operator->>Tool: Restore
    Tool->>Tool: Verify simulation input, safeguard, and plan hashes
    Tool->>Dest: GET fresh pre-restore destination state
    Tool->>Tool: Block if destination state or exact plan changed
    Tool->>Files: Start atomic per-operation execution journal
    Tool->>Dest: POST/PUT/DELETE in dependency order
    Dest-->>Tool: Write results
    Tool->>Dest: GET post-restore destination state
    Tool->>Files: Write restore result, residual diff, and verification report
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
    Dependency -- yes --> Simulation[Offline Simulation]
    Simulation --> References{Required references resolvable?}
    References -- no --> BlockSimulation[Simulation artifact records blockers]
    References -- yes --> Reviewed{Matching reviewed simulation supplied?}
    Reviewed -- no --> BlockRestore[Restore blocks by default]
    Reviewed -- yes --> Restore{Operator confirms Restore?}
    Restore -- no --> Stop[No tenant changes]
    Restore -- yes --> Fresh[Capture fresh destination and recheck plan]
    Fresh --> Drift{Destination drift?}
    Drift -- yes --> BlockDrift[Block before writes]
    Drift -- no --> Apply[Write to Destination]
```

Validate decrypts encrypted backups before checking file integrity and structure. Preflight checks whether the restore set is internally consistent. The offline simulation then verifies request ordering, payload preparation, cross-tenant ID mapping, and safety skips before write operations are allowed.

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

Backup policy scope and restore selection are separate. The Scope tab or
`--select`/`--select-resource` filters which differences may become restore
operations. A selective diff persists canonical stable identities and is
recomputed by preflight. Dependencies remain validation-only unless
`--include-dependencies` is selected, and policy bulk reorder remains excluded
unless `--restore-policy-order` is selected.

```mermaid
flowchart TD
    Desired[(Desired backup)] --> Select{Restore scope}
    Select --> Complete[Complete backup scope]
    Select --> Objects[One or more stable object selectors]
    Select --> Domain[Whole writable resource type]
    Objects --> Dependencies{Include writable dependencies?}
    Domain --> Dependencies
    Dependencies -- no --> ValidateOnly[Validate mappings only]
    Dependencies -- yes --> Expand[Recursively add referenced writable objects]
    ValidateOnly --> ScopedDiff[Persist scoped diff]
    Expand --> ScopedDiff
    ScopedDiff --> Simulation[Scoped simulation and assurance]
    Simulation --> Writes[Selected writes only]
    Writes --> Residual[Scoped residual verification]
```

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
    RestoreDiff --> SimulationResult[(timestamp-simulation.json/html)]
    RestoreDiff --> RestoreResult[(timestamp-restore-result.json/html)]
```

Every significant operation writes local artifacts so an operator can review what happened and rerun validation/reporting from files.

## Disaster Recovery Checklist Flow

```mermaid
flowchart TD
    Backup[(Desired backup JSON or JSON.enc)] --> Generate[DR generate<br/>offline and credential-free]
    Coverage[30 modeled domains<br/>136 explicit operations] --> Generate
    Exclusions[Known external recovery areas] --> Generate
    Generate --> JSON[(Canonical runbook JSON)]
    Generate --> HTML[(Printable HTML checklist)]

    JSON --> Status[DR status]
    Status --> Execute[Perform one documented recovery step]
    Execute --> Evidence[Collect non-secret evidence]
    Evidence --> Check[DR check<br/>actor + status + evidence]
    Check --> Chain[Append hash-chained checklist event]
    Chain --> JSON
    Chain --> HTML

    JSON --> Verify[DR verify]
    Verify --> SourceHash{Source artifact hash valid?}
    SourceHash --> PlanHash{Plan, state, chain,<br/>summary hashes valid?}
    PlanHash --> Complete{Every required item<br/>addressed?}
    Complete --> Archive[Archive recovery evidence set]
```

The checklist contains readiness and change-control gates, every modeled
domain, every captured setting, known exclusions, post-restore technical and
business validation, audit-ledger verification, evidence retention, and final
acceptance. Automated commands are emitted only for stable writable resources;
all other modes have explicit manual or verification procedures.

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
| Restore selected objects | `Scope` + `Build Restore Plan` | `zpa_cloner.py restore-plan --select <selector>` | None while planning; Destination only after reviewed restore |
| Validate files | `Validate` | `zpa_cloner.py validate` | None |
| Preflight restore | `Preflight` | `zpa_cloner.py preflight` | None |
| Simulate restore | `Simulate` | `python3 -m zpa_backup_restore simulate` | None; credentials not required |
| Apply restore | `Restore` | `zpa_cloner.py restore --simulation <reviewed.json> --yes` | Destination only |
| Generate report | `Report` | `zpa_cloner.py report` | None |
| Generate DR runbook | `DR Runbook` | `python3 -m zpa_backup_restore dr generate --source-backup <backup>` | None; credentials not required |
| Show coverage | `Coverage` | `zpa_cloner.py coverage` | None |
| Edit one rule | Not part of main UI | `zpa_policy_tool.py add-scim-criteria --apply` | Configured single tenant |
