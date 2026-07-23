"""Immutable domain records for managed snapshots and inventory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    snapshot_id: str
    tenant_fingerprint: str
    tenant_label: str
    customer_hint: str
    captured_at: str
    imported_at: str
    artifact_path: str
    artifact_sha256: str
    content_sha256: str
    encrypted: bool
    schema_version: str
    application_version: str
    error_count: int
    warning_count: int
    resource_count: int
    verified: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InventoryResource:
    snapshot_id: str
    resource_type: str
    stable_key: str
    display_name: str
    source_id: str
    config_sha256: str
    writable: bool
    high_impact: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InventoryReference:
    snapshot_id: str
    from_resource_type: str
    from_stable_key: str
    field_path: str
    target_resource_type: str
    target_stable_key: str
    target_source_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InventoryDriftEntry:
    resource_type: str
    stable_key: str
    display_name: str
    status: str
    from_config_sha256: str | None
    to_config_sha256: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InventoryDrift:
    from_snapshot_id: str
    to_snapshot_id: str
    same_tenant: bool
    entries: tuple[InventoryDriftEntry, ...]

    @property
    def summary(self) -> dict[str, int]:
        counts = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
        for entry in self.entries:
            counts[entry.status] += 1
        return counts

    def as_dict(self, *, include_unchanged: bool = True) -> dict[str, Any]:
        entries = self.entries
        if not include_unchanged:
            entries = tuple(entry for entry in entries if entry.status != "unchanged")
        return {
            "fromSnapshotId": self.from_snapshot_id,
            "toSnapshotId": self.to_snapshot_id,
            "sameTenant": self.same_tenant,
            "summary": self.summary,
            "entries": [entry.as_dict() for entry in entries],
        }


@dataclass(frozen=True, slots=True)
class LedgerVerification:
    valid: bool
    event_count: int
    run_count: int
    head_hash: str
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
