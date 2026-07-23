"""Repository protocol for managed snapshot and inventory persistence."""

from __future__ import annotations

from typing import Protocol

from zpa_backup_restore.domain.models import InventoryReference, InventoryResource, SnapshotRecord


class SnapshotCatalog(Protocol):
    def register_snapshot(
        self,
        snapshot: SnapshotRecord,
        resources: list[InventoryResource],
        references: list[InventoryReference],
    ) -> None: ...

    def get_snapshot(self, snapshot_id: str) -> SnapshotRecord | None: ...

    def list_snapshots(
        self,
        *,
        tenant_fingerprint: str | None = None,
        limit: int = 100,
    ) -> list[SnapshotRecord]: ...

    def list_resources(
        self,
        *,
        snapshot_id: str | None = None,
        resource_type: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[InventoryResource]: ...

    def resource_history(
        self,
        *,
        resource_type: str,
        stable_key: str,
        limit: int = 100,
    ) -> list[tuple[SnapshotRecord, InventoryResource]]: ...

    def list_references(
        self,
        *,
        snapshot_id: str,
        resource_type: str | None = None,
        stable_key: str | None = None,
        direction: str = "outgoing",
        limit: int = 500,
    ) -> list[InventoryReference]: ...

    def close(self) -> None: ...
