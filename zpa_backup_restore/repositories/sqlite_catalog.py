"""SQLite snapshot catalog with explicit schema migration."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from zpa_backup_restore.domain.models import InventoryReference, InventoryResource, SnapshotRecord
from zpa_backup_restore.errors import CliError


CATALOG_SCHEMA_VERSION = 1
DEFAULT_CATALOG_PATH = Path("state/catalog.sqlite3")


class SQLiteSnapshotCatalog:
    """Local metadata index; complete resource payloads are never stored."""

    def __init__(self, path: Path = DEFAULT_CATALOG_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._migrate()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _migrate(self) -> None:
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current > CATALOG_SCHEMA_VERSION:
            raise CliError(
                f"Catalog schema {current} is newer than supported schema {CATALOG_SCHEMA_VERSION}: {self.path}"
            )
        if current < 1:
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        tenant_fingerprint TEXT NOT NULL,
                        tenant_label TEXT NOT NULL,
                        customer_hint TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        imported_at TEXT NOT NULL,
                        artifact_path TEXT NOT NULL,
                        artifact_sha256 TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        encrypted INTEGER NOT NULL CHECK (encrypted IN (0, 1)),
                        schema_version TEXT NOT NULL,
                        application_version TEXT NOT NULL,
                        error_count INTEGER NOT NULL,
                        warning_count INTEGER NOT NULL,
                        resource_count INTEGER NOT NULL,
                        verified INTEGER NOT NULL CHECK (verified IN (0, 1))
                    );

                    CREATE INDEX snapshots_tenant_time
                        ON snapshots (tenant_fingerprint, captured_at DESC);

                    CREATE TABLE inventory_resources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                        resource_type TEXT NOT NULL,
                        stable_key TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        config_sha256 TEXT NOT NULL,
                        writable INTEGER NOT NULL CHECK (writable IN (0, 1)),
                        high_impact INTEGER NOT NULL CHECK (high_impact IN (0, 1)),
                        UNIQUE (snapshot_id, resource_type, stable_key, source_id)
                    );

                    CREATE INDEX inventory_resource_lookup
                        ON inventory_resources (resource_type, stable_key, snapshot_id);
                    CREATE INDEX inventory_resource_name
                        ON inventory_resources (display_name, resource_type);

                    CREATE TABLE inventory_references (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
                        from_resource_type TEXT NOT NULL,
                        from_stable_key TEXT NOT NULL,
                        field_path TEXT NOT NULL,
                        target_resource_type TEXT NOT NULL,
                        target_stable_key TEXT NOT NULL,
                        target_source_id TEXT NOT NULL,
                        UNIQUE (
                            snapshot_id,
                            from_resource_type,
                            from_stable_key,
                            field_path,
                            target_resource_type,
                            target_stable_key,
                            target_source_id
                        )
                    );

                    CREATE INDEX inventory_reference_outgoing
                        ON inventory_references (snapshot_id, from_resource_type, from_stable_key);
                    CREATE INDEX inventory_reference_incoming
                        ON inventory_references (snapshot_id, target_resource_type, target_stable_key);
                    """
                )
                self.connection.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> SnapshotRecord:
        return SnapshotRecord(
            snapshot_id=row["snapshot_id"],
            tenant_fingerprint=row["tenant_fingerprint"],
            tenant_label=row["tenant_label"],
            customer_hint=row["customer_hint"],
            captured_at=row["captured_at"],
            imported_at=row["imported_at"],
            artifact_path=row["artifact_path"],
            artifact_sha256=row["artifact_sha256"],
            content_sha256=row["content_sha256"],
            encrypted=bool(row["encrypted"]),
            schema_version=row["schema_version"],
            application_version=row["application_version"],
            error_count=int(row["error_count"]),
            warning_count=int(row["warning_count"]),
            resource_count=int(row["resource_count"]),
            verified=bool(row["verified"]),
        )

    @staticmethod
    def _resource(row: sqlite3.Row) -> InventoryResource:
        return InventoryResource(
            snapshot_id=row["snapshot_id"],
            resource_type=row["resource_type"],
            stable_key=row["stable_key"],
            display_name=row["display_name"],
            source_id=row["source_id"],
            config_sha256=row["config_sha256"],
            writable=bool(row["writable"]),
            high_impact=bool(row["high_impact"]),
        )

    @staticmethod
    def _reference(row: sqlite3.Row) -> InventoryReference:
        return InventoryReference(
            snapshot_id=row["snapshot_id"],
            from_resource_type=row["from_resource_type"],
            from_stable_key=row["from_stable_key"],
            field_path=row["field_path"],
            target_resource_type=row["target_resource_type"],
            target_stable_key=row["target_stable_key"],
            target_source_id=row["target_source_id"],
        )

    def register_snapshot(
        self,
        snapshot: SnapshotRecord,
        resources: list[InventoryResource],
        references: list[InventoryReference],
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id, tenant_fingerprint, tenant_label, customer_hint,
                    captured_at, imported_at, artifact_path, artifact_sha256,
                    content_sha256, encrypted, schema_version, application_version,
                    error_count, warning_count, resource_count, verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    artifact_path = excluded.artifact_path,
                    artifact_sha256 = excluded.artifact_sha256,
                    imported_at = excluded.imported_at,
                    verified = excluded.verified
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.tenant_fingerprint,
                    snapshot.tenant_label,
                    snapshot.customer_hint,
                    snapshot.captured_at,
                    snapshot.imported_at,
                    snapshot.artifact_path,
                    snapshot.artifact_sha256,
                    snapshot.content_sha256,
                    int(snapshot.encrypted),
                    snapshot.schema_version,
                    snapshot.application_version,
                    snapshot.error_count,
                    snapshot.warning_count,
                    snapshot.resource_count,
                    int(snapshot.verified),
                ),
            )
            self.connection.execute(
                "DELETE FROM inventory_references WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            )
            self.connection.execute(
                "DELETE FROM inventory_resources WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            )
            self.connection.executemany(
                """
                INSERT INTO inventory_resources (
                    snapshot_id, resource_type, stable_key, display_name, source_id,
                    config_sha256, writable, high_impact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        resource.snapshot_id,
                        resource.resource_type,
                        resource.stable_key,
                        resource.display_name,
                        resource.source_id,
                        resource.config_sha256,
                        int(resource.writable),
                        int(resource.high_impact),
                    )
                    for resource in resources
                ],
            )
            self.connection.executemany(
                """
                INSERT INTO inventory_references (
                    snapshot_id, from_resource_type, from_stable_key, field_path,
                    target_resource_type, target_stable_key, target_source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        reference.snapshot_id,
                        reference.from_resource_type,
                        reference.from_stable_key,
                        reference.field_path,
                        reference.target_resource_type,
                        reference.target_stable_key,
                        reference.target_source_id,
                    )
                    for reference in references
                ],
            )

    def get_snapshot(self, snapshot_id: str) -> SnapshotRecord | None:
        row = self.connection.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return self._snapshot(row) if row else None

    def list_snapshots(
        self,
        *,
        tenant_fingerprint: str | None = None,
        limit: int = 100,
    ) -> list[SnapshotRecord]:
        sql = "SELECT * FROM snapshots"
        values: list[object] = []
        if tenant_fingerprint:
            sql += " WHERE tenant_fingerprint = ?"
            values.append(tenant_fingerprint)
        sql += " ORDER BY captured_at DESC, imported_at DESC LIMIT ?"
        values.append(max(1, limit))
        return [self._snapshot(row) for row in self.connection.execute(sql, values)]

    def list_resources(
        self,
        *,
        snapshot_id: str | None = None,
        resource_type: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[InventoryResource]:
        clauses = []
        values: list[object] = []
        if snapshot_id:
            clauses.append("snapshot_id = ?")
            values.append(snapshot_id)
        if resource_type:
            clauses.append("resource_type = ?")
            values.append(resource_type)
        if search:
            clauses.append("(display_name LIKE ? COLLATE NOCASE OR stable_key LIKE ? COLLATE NOCASE)")
            pattern = f"%{search}%"
            values.extend((pattern, pattern))
        sql = "SELECT * FROM inventory_resources"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY resource_type, display_name, stable_key LIMIT ?"
        values.append(max(1, limit))
        return [self._resource(row) for row in self.connection.execute(sql, values)]

    def resource_history(
        self,
        *,
        resource_type: str,
        stable_key: str,
        limit: int = 100,
    ) -> list[tuple[SnapshotRecord, InventoryResource]]:
        rows = self.connection.execute(
            """
            SELECT
                s.*,
                r.snapshot_id AS r_snapshot_id,
                r.resource_type AS r_resource_type,
                r.stable_key AS r_stable_key,
                r.display_name AS r_display_name,
                r.source_id AS r_source_id,
                r.config_sha256 AS r_config_sha256,
                r.writable AS r_writable,
                r.high_impact AS r_high_impact
            FROM inventory_resources r
            JOIN snapshots s ON s.snapshot_id = r.snapshot_id
            WHERE r.resource_type = ? AND r.stable_key = ?
            ORDER BY s.captured_at DESC, s.imported_at DESC
            LIMIT ?
            """,
            (resource_type, stable_key, max(1, limit)),
        ).fetchall()
        history = []
        for row in rows:
            resource = InventoryResource(
                snapshot_id=row["r_snapshot_id"],
                resource_type=row["r_resource_type"],
                stable_key=row["r_stable_key"],
                display_name=row["r_display_name"],
                source_id=row["r_source_id"],
                config_sha256=row["r_config_sha256"],
                writable=bool(row["r_writable"]),
                high_impact=bool(row["r_high_impact"]),
            )
            history.append((self._snapshot(row), resource))
        return history

    def list_references(
        self,
        *,
        snapshot_id: str,
        resource_type: str | None = None,
        stable_key: str | None = None,
        direction: str = "outgoing",
        limit: int = 500,
    ) -> list[InventoryReference]:
        if direction not in {"outgoing", "incoming"}:
            raise CliError("Reference direction must be outgoing or incoming")
        prefix = "from" if direction == "outgoing" else "target"
        clauses = ["snapshot_id = ?"]
        values: list[object] = [snapshot_id]
        if resource_type:
            clauses.append(f"{prefix}_resource_type = ?")
            values.append(resource_type)
        if stable_key:
            clauses.append(f"{prefix}_stable_key = ?")
            values.append(stable_key)
        sql = (
            "SELECT * FROM inventory_references WHERE "
            + " AND ".join(clauses)
            + " ORDER BY from_resource_type, from_stable_key, field_path LIMIT ?"
        )
        values.append(max(1, limit))
        return [self._reference(row) for row in self.connection.execute(sql, values)]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteSnapshotCatalog":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["CATALOG_SCHEMA_VERSION", "DEFAULT_CATALOG_PATH", "SQLiteSnapshotCatalog"]
