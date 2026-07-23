"""Credential-free inventory queries and snapshot-to-snapshot drift analysis."""

from __future__ import annotations

from zpa_backup_restore.domain.models import (
    InventoryDrift,
    InventoryDriftEntry,
    InventoryReference,
    InventoryResource,
    SnapshotRecord,
)
from zpa_backup_restore.repositories.catalog import SnapshotCatalog
from zpa_backup_restore.services.snapshots import SnapshotService


class InventoryService:
    """Application boundary for inventory browsing, history, references, and drift."""

    def __init__(self, catalog: SnapshotCatalog) -> None:
        self.catalog = catalog
        self.snapshots = SnapshotService(catalog)

    def list_resources(
        self,
        *,
        snapshot_identifier: str = "latest",
        resource_type: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> tuple[SnapshotRecord | None, list[InventoryResource]]:
        snapshot = None
        snapshot_id = None
        if snapshot_identifier != "all":
            snapshot = self.snapshots.resolve_snapshot(snapshot_identifier)
            snapshot_id = snapshot.snapshot_id
        return snapshot, self.catalog.list_resources(
            snapshot_id=snapshot_id,
            resource_type=resource_type,
            search=search,
            limit=limit,
        )

    def history(
        self,
        *,
        resource_type: str,
        stable_key: str,
        limit: int = 100,
    ) -> list[tuple[SnapshotRecord, InventoryResource]]:
        return self.catalog.resource_history(
            resource_type=resource_type,
            stable_key=stable_key,
            limit=limit,
        )

    def references(
        self,
        *,
        snapshot_identifier: str,
        resource_type: str | None = None,
        stable_key: str | None = None,
        direction: str = "outgoing",
        limit: int = 500,
    ) -> tuple[SnapshotRecord, list[InventoryReference]]:
        snapshot = self.snapshots.resolve_snapshot(snapshot_identifier)
        return snapshot, self.catalog.list_references(
            snapshot_id=snapshot.snapshot_id,
            resource_type=resource_type,
            stable_key=stable_key,
            direction=direction,
            limit=limit,
        )

    def drift(
        self,
        from_identifier: str,
        to_identifier: str,
    ) -> InventoryDrift:
        before = self.snapshots.resolve_snapshot(from_identifier)
        after = self.snapshots.resolve_snapshot(to_identifier)
        before_resources = self.catalog.list_resources(snapshot_id=before.snapshot_id, limit=1_000_000)
        after_resources = self.catalog.list_resources(snapshot_id=after.snapshot_id, limit=1_000_000)

        def by_identity(resources: list[InventoryResource]) -> dict[tuple[str, str], InventoryResource]:
            return {(resource.resource_type, resource.stable_key): resource for resource in resources}

        before_index = by_identity(before_resources)
        after_index = by_identity(after_resources)
        entries: list[InventoryDriftEntry] = []
        for resource_type, stable_key in sorted(set(before_index) | set(after_index)):
            old = before_index.get((resource_type, stable_key))
            new = after_index.get((resource_type, stable_key))
            if old is None:
                status = "added"
            elif new is None:
                status = "removed"
            elif old.config_sha256 != new.config_sha256:
                status = "changed"
            else:
                status = "unchanged"
            entries.append(
                InventoryDriftEntry(
                    resource_type=resource_type,
                    stable_key=stable_key,
                    display_name=(new or old).display_name,
                    status=status,
                    from_config_sha256=old.config_sha256 if old else None,
                    to_config_sha256=new.config_sha256 if new else None,
                )
            )
        return InventoryDrift(
            from_snapshot_id=before.snapshot_id,
            to_snapshot_id=after.snapshot_id,
            same_tenant=before.tenant_fingerprint == after.tenant_fingerprint,
            entries=tuple(entries),
        )


__all__ = ["InventoryService"]
