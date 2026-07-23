# Version 2 Architecture

## Design Goal

Version 2 keeps the existing operator workflow and safety controls while making
API coverage easier to extend. The core design is hybrid: one composition
module per ZPA resource or closely related API domain, plus one small
declarative module per modeled HTTP action, backed by shared transport and
workflow services.

The project remains an independent tool and is not affiliated with, endorsed by, sponsored by, certified by, or supported by Zscaler, Inc. See [../DISCLAIMER.md](../DISCLAIMER.md).

## Source Tree

```text
zpa_backup_restore/
├── cli.py                  # command parsing and workflow orchestration
├── errors.py               # shared expected errors
├── security.py             # shared persisted-artifact redaction
├── version.py              # single release version
├── domain/                 # immutable snapshot, inventory, drift, and audit records
├── repositories/           # persistence protocols plus SQLite/JSONL adapters
├── services/
│   ├── snapshots.py        # snapshot registration, verification, and safe indexing
│   ├── inventory.py        # search, history, references, and drift
│   ├── audits.py           # run audit queries
│   ├── assurance.py        # reviewed-plan hashes and destination drift gate
│   └── execution_journal.py # atomic per-operation restore state
├── api/                    # stable transport and audit boundary
├── core/
│   ├── backup.py           # read-only backup service and pagination
│   ├── catalog.py          # compatibility view of the resource registry
│   ├── diff.py             # pure name-based comparison
│   ├── integrity.py        # manifests, validation, and preflight
│   ├── mapping.py          # cross-tenant ID remapping
│   ├── selection.py        # stable selective-restore scope and diff filtering
│   ├── restore.py          # guarded writes in dependency order
│   └── simulation.py       # offline ordered request and payload planning
├── resources/
│   ├── model.py            # typed ResourceSpec + OperationSpec contracts
│   ├── registry.py         # ordered composition of resource modules
│   ├── operations/         # domain packages; one module per HTTP action
│   ├── application_segments.py
│   ├── policy_rules.py
│   └── ...                 # one file per resource/API domain
├── storage/
│   └── backups.py          # JSON and OpenSSL-compatible encryption
└── reporting/
    └── html_report.py      # redacted HTML output
```

The top-level `zpa_cloner.py`, `zpa_resources.py`, `zpa_integrity.py`, and `zpa_report.py` files are compatibility façades. New implementation work belongs in the package.

The API package currently adapts the proven transport and audit implementation also used by the backward-compatible single-rule CLI. This keeps one authentication and redaction implementation while resource actions move independently. The adapter boundary allows the transport to be moved without changing resource or workflow modules.

## Operation Modules Inside Domain Packages

The endpoint catalog uses one small declarative module per documented HTTP
action, grouped by domain. For example, `operations/server_groups/` contains
separate list, get, create, update, and delete declarations, while
`server_groups.py` composes them into one resource definition.

An operation module contains only auditable facts:

- method and path;
- action/role and pagination style;
- official documentation slug;
- high-impact classification;
- support status: `enabled`, `catalog-only`, or `excluded`.

It does not contain authentication, request, retry, pagination, audit, redaction,
or error-handling code. Those mechanics stay in shared services, so operation
files remain small rather than duplicating transport logic.

A resource/domain module owns:

- the set of composed operations;
- dependency order;
- stable identity and reference mapping;
- write-skip fields;
- safety flags such as high impact;
- resource-specific behavior.

The generic services perform ordinary actions from those declarations. A
resource module records exceptions close to the endpoint—for example,
`application_segments.py` declares that the paginated list response is already
detailed, so backup skips per-item GET calls. Its move/share operations remain
separate, high-impact operations.

This separation also distinguishes discovery from execution. Sensitive
Business Continuity writes and operational Emergency Access actions are visible
in coverage as `catalog-only`, but the restore engine cannot execute them.

## Adding Or Changing API Coverage

1. Add one operation file under the matching
   `zpa_backup_restore/resources/operations/<domain>/` package.
2. Declare method, path, role, pagination, documentation slug, impact, and
   support status in its `OperationSpec`.
3. Export it from that domain package and compose it into the owning
   `ResourceSpec`.
4. Register a new resource in `resources/registry.py`; add it to
   `MIGRATION_ORDER` only when writes are enabled and dependencies are ordered.
5. Put exceptional identity, payload, or association behavior in the resource
   module and shared workflow. Do not duplicate transport mechanics.
6. Add endpoint, backup, diff, mapping, simulation, and live-executor tests
   appropriate to the operation's risk before changing it to `enabled`.
7. Refresh the official sitemap audit and operator documentation.

## Dependency Direction

```text
CLI / UI
   ↓
backup and restore services
   ↓
resource modules + shared API client

diff / mapping / integrity / reporting
   ↓
resource registry only (no tenant credentials or network)
```

Pure modules can be tested with JSON dictionaries. Simulation is also pure and credential-free: planned creates use symbolic deferred references until the live API returns their destination IDs. Only backup and live restore services need an API client, and source workflows never receive a write operation.

Managed recovery follows ports-and-adapters dependency direction:

```text
CLI / desktop UI
        ↓
application services (snapshots, inventory, audit, assurance)
        ↓
domain records + repository protocols
        ↓
SQLite catalog / hash-chained JSONL ledger / files

application services → pure core → resource declarations
live workflows       → API adapter
```

The SQLite catalog deliberately stores searchable metadata and configuration hashes, not complete resource payloads. Backup artifacts remain the source of truth. The run ledger and execution journal are separate: the ledger correlates commands and artifact hashes across runs; the journal records each restore operation before and after its destination call.

## Selective Restore Boundary

Selective restore is implemented at the pure diff boundary, not by deleting
operations from generated JSON. `core/selection.py` resolves requested objects
against the desired backup using the same stable identities as the diff engine,
optionally expands referenced writable dependencies, filters ordinary and
special-operation sections, and persists the resolved scope in the diff.

Every later stage consumes the persisted scope:

```text
stable selectors → scoped diff → scoped simulation + assurance
                                      ↓
fresh destination → recomputed scoped plan → selected writes only
                                      ↓
post snapshot → scoped residual verification
```

This makes the recovery scope reproducible and auditable. Preflight rejects a
scoped diff whose operations no longer match its desired backup, reviewed
target, and scope. Assurance hashes include the scope and exact operation plan.
Fresh-target state hashing and residual comparison are scoped as well, so
unrelated tenant changes neither block nor falsely fail a targeted recovery.

Dependency inclusion is explicit because silently widening a restore would
violate operator intent. Read-only dependencies are mapping inputs, never write
targets. Policy order is also explicit because its bulk endpoint affects an
entire policy type even when only one rule was selected.

## Restore Assurance Boundary

An offline simulation binds the desired backup, reviewed destination backup, diff, normalized destination state, safeguard selections, and exact ordered operations with SHA-256 hashes. Live restore validates that artifact before credentials are loaded. It then captures a new destination backup and requires both the normalized state and recomputed ordered plan to match before writing.

The sequence is:

```text
reviewed files → assured simulation → operator review
       ↓
live restore validates hashes
       ↓
fresh destination snapshot → state/plan drift check
       ↓
atomic execution journal → guarded writes
       ↓
post snapshot → residual diff/report
```

`--allow-unreviewed-plan` exists only as an explicit compatibility escape hatch and produces a run-ledger event. It does not disable the fresh pre-restore backup or post-restore verification.

## Compatibility

- Canonical v2 command: `python3 -m zpa_backup_restore`.
- Installed command: `zpa-backup-restore`.
- Legacy command: `python3 zpa_cloner.py`.
- Existing backup schema: `1.0`.
- Package/application release: `2.0.0`.

The backup schema is intentionally independent of the application version. Existing valid v1 backups remain readable in v2.
