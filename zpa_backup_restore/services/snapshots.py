"""Managed snapshot registration, safe inventory extraction, and verification."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterator

from zpa_backup_restore import __version__
from zpa_backup_restore.core.catalog import RESOURCES
from zpa_backup_restore.core.diff import identity_key, normalize_name, strip_compare
from zpa_backup_restore.core.integrity import backup_digest, canonical_json, validate_backup
from zpa_backup_restore.domain.models import InventoryReference, InventoryResource, SnapshotRecord
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.repositories.catalog import SnapshotCatalog


BackupLoader = Callable[[Path], Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tenant_fingerprint(customer_id: Any) -> str:
    return hashlib.sha256(str(customer_id).encode("utf-8")).hexdigest()


def _resource_items(resource_type: str, value: Any) -> Iterator[tuple[str | None, dict[str, Any]]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield None, item
    elif isinstance(value, dict):
        for catalog_key, item in value.items():
            if isinstance(item, dict):
                yield str(catalog_key), item


def _display_name(item: dict[str, Any], catalog_key: str | None = None) -> str:
    return str(
        item.get("name")
        or item.get("displayName")
        or item.get("policyType")
        or catalog_key
        or item.get("id")
        or "(unnamed)"
    )


def _stable_key(resource_type: str, item: dict[str, Any], catalog_key: str | None = None) -> str:
    if resource_type == "policy_rules":
        return identity_key(item, "name")
    if resource_type in {"scim_attributes", "scim_groups"}:
        scope = normalize_name(item.get("_idpName") or item.get("_idpId") or "")
        return f"{scope}:{normalize_name(_display_name(item, catalog_key))}"
    if catalog_key:
        return normalize_name(catalog_key)
    meta = RESOURCES.get(resource_type, {})
    return identity_key(item, meta.get("name_field", "name"))


def _normalized_config(resource_type: str, item: dict[str, Any]) -> Any:
    skip = set(RESOURCES.get(resource_type, {}).get("skip_fields", set()))
    if resource_type == "policy_rules":
        skip.update({"policySetId", "ruleOrder"})
    return strip_compare(item, skip)


def _resource_safety(resource_type: str) -> tuple[bool, bool]:
    if resource_type == "policy_rules":
        return True, False
    meta = RESOURCES.get(resource_type, {})
    return bool(meta.get("writable", False)), bool(meta.get("high_impact", False))


def _walk_values(value: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f"{path}[{index}]")
    else:
        yield path, value


def build_inventory(
    snapshot_id: str,
    backup: dict[str, Any],
) -> tuple[list[InventoryResource], list[InventoryReference]]:
    """Extract metadata and reference edges without retaining resource payloads."""
    resources: list[InventoryResource] = []
    source_records: list[tuple[InventoryResource, dict[str, Any]]] = []
    id_index: dict[str, list[InventoryResource]] = defaultdict(list)
    seen_keys: defaultdict[tuple[str, str], int] = defaultdict(int)

    for resource_type, value in backup.get("resources", {}).items():
        for catalog_key, item in _resource_items(resource_type, value):
            stable_key = _stable_key(resource_type, item, catalog_key)
            resource_meta = RESOURCES.get(resource_type, {})
            source_id = str(
                item.get(resource_meta.get("id_field", "id"))
                or item.get("policySetId")
                or ""
            )
            duplicate_key = (resource_type, stable_key)
            seen_keys[duplicate_key] += 1
            if seen_keys[duplicate_key] > 1:
                stable_key = f"{stable_key}#duplicate-{seen_keys[duplicate_key]}"
            writable, high_impact = _resource_safety(resource_type)
            record = InventoryResource(
                snapshot_id=snapshot_id,
                resource_type=resource_type,
                stable_key=stable_key,
                display_name=_display_name(item, catalog_key),
                source_id=source_id,
                config_sha256=hashlib.sha256(
                    canonical_json(_normalized_config(resource_type, item)).encode("utf-8")
                ).hexdigest(),
                writable=writable,
                high_impact=high_impact,
            )
            resources.append(record)
            source_records.append((record, item))
            if source_id:
                id_index[source_id].append(record)

    references: list[InventoryReference] = []
    seen_references: set[tuple[str, ...]] = set()
    for source, payload in source_records:
        for field_path, value in _walk_values(payload):
            if field_path == "$.id":
                continue
            targets = id_index.get(str(value), [])
            for target in targets:
                if (
                    target.resource_type == source.resource_type
                    and target.stable_key == source.stable_key
                ):
                    continue
                key = (
                    source.resource_type,
                    source.stable_key,
                    field_path,
                    target.resource_type,
                    target.stable_key,
                    target.source_id,
                )
                if key in seen_references:
                    continue
                seen_references.add(key)
                references.append(
                    InventoryReference(
                        snapshot_id=snapshot_id,
                        from_resource_type=source.resource_type,
                        from_stable_key=source.stable_key,
                        field_path=field_path,
                        target_resource_type=target.resource_type,
                        target_stable_key=target.stable_key,
                        target_source_id=target.source_id,
                    )
                )
    return resources, references


class SnapshotService:
    def __init__(self, catalog: SnapshotCatalog) -> None:
        self.catalog = catalog

    def register_backup(
        self,
        backup: dict[str, Any],
        artifact_path: Path,
        *,
        require_valid: bool = True,
    ) -> SnapshotRecord:
        issues = validate_backup(backup, strict=True)
        if issues and require_valid:
            raise CliError(
                "Cannot register invalid backup:\n" + "\n".join(f"- {issue}" for issue in issues)
            )
        if not artifact_path.is_file():
            raise CliError(f"Snapshot artifact does not exist: {artifact_path}")

        manifest = backup.get("manifest", {}) if isinstance(backup.get("manifest"), dict) else {}
        content_sha256 = str(manifest.get("sha256") or backup_digest(backup))
        snapshot_id = content_sha256
        customer_id = str(backup.get("meta", {}).get("customerId") or "")
        resources, references = build_inventory(snapshot_id, backup)
        snapshot = SnapshotRecord(
            snapshot_id=snapshot_id,
            tenant_fingerprint=tenant_fingerprint(customer_id),
            tenant_label=str(backup.get("meta", {}).get("label") or "tenant"),
            customer_hint=customer_id[-4:] if customer_id else "",
            captured_at=str(backup.get("meta", {}).get("timestamp") or ""),
            imported_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            artifact_path=str(artifact_path.resolve()),
            artifact_sha256=sha256_file(artifact_path),
            content_sha256=content_sha256,
            encrypted=artifact_path.name.endswith(".enc"),
            schema_version=str(manifest.get("schemaVersion") or "unknown"),
            application_version=__version__,
            error_count=len(backup.get("errors", {}) or {}),
            warning_count=len(backup.get("warnings", []) or []),
            resource_count=len(resources),
            verified=not issues,
        )
        self.catalog.register_snapshot(snapshot, resources, references)
        return snapshot

    def import_backup(self, artifact_path: Path, loader: BackupLoader) -> SnapshotRecord:
        backup = loader(artifact_path)
        if not isinstance(backup, dict):
            raise CliError(f"Backup root must be an object: {artifact_path}")
        return self.register_backup(backup, artifact_path)

    def resolve_snapshot(self, identifier: str) -> SnapshotRecord:
        if identifier == "latest":
            snapshots = self.catalog.list_snapshots(limit=1)
            if not snapshots:
                raise CliError("The snapshot catalog is empty")
            return snapshots[0]
        exact = self.catalog.get_snapshot(identifier)
        if exact:
            return exact
        matches = [
            snapshot
            for snapshot in self.catalog.list_snapshots(limit=10_000)
            if snapshot.snapshot_id.startswith(identifier)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CliError(f"Snapshot ID prefix is ambiguous: {identifier}")
        raise CliError(f"Snapshot not found: {identifier}")

    def verify_snapshot(self, identifier: str, loader: BackupLoader) -> SnapshotRecord:
        snapshot = self.resolve_snapshot(identifier)
        path = Path(snapshot.artifact_path)
        if not path.is_file():
            raise CliError(f"Snapshot artifact is missing: {path}")
        if sha256_file(path) != snapshot.artifact_sha256:
            raise CliError(f"Snapshot artifact SHA-256 mismatch: {path}")
        backup = loader(path)
        issues = validate_backup(backup, strict=True)
        if issues:
            raise CliError(
                "Snapshot backup validation failed:\n" + "\n".join(f"- {issue}" for issue in issues)
            )
        if backup_digest(backup) != snapshot.content_sha256:
            raise CliError(f"Snapshot content SHA-256 mismatch: {path}")
        return self.register_backup(backup, path)


__all__ = [
    "SnapshotService",
    "build_inventory",
    "sha256_file",
    "tenant_fingerprint",
]
