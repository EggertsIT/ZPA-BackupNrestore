import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore.cli import main
from zpa_backup_restore.core.integrity import attach_manifest
from zpa_backup_restore.repositories.sqlite_catalog import (
    CATALOG_SCHEMA_VERSION,
    SQLiteSnapshotCatalog,
)
from zpa_backup_restore.services.inventory import InventoryService
from zpa_backup_restore.services.snapshots import SnapshotService
from zpa_backup_restore.storage.backups import load_json_file, save_json


class SnapshotCatalogTests(unittest.TestCase):
    def backup(self, *, timestamp: str, description: str = "original") -> dict:
        return attach_manifest(
            {
                "meta": {
                    "label": "production",
                    "timestamp": timestamp,
                    "customerId": "customer-sensitive-1234",
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": {
                    "microtenants": [],
                    "inspection_custom_controls": [],
                    "inspection_profiles": [],
                    "cbi_profiles": [],
                    "app_connector_groups": [],
                    "service_edge_groups": [],
                    "segment_groups": [],
                    "servers": [
                        {
                            "id": "server-1",
                            "name": "Inventory Server",
                            "serverGroupId": "server-group-1",
                            "description": description,
                            "clientSecret": "never-store-this-secret",
                        }
                    ],
                    "server_groups": [{"id": "server-group-1", "name": "Primary Group"}],
                    "application_segments": [],
                    "lss_configs": [],
                    "pra_portals": [],
                    "pra_consoles": [],
                    "policy_rules": [],
                    "idps": [],
                    "scim_attributes": [],
                    "scim_groups": [],
                    "policy_sets": {},
                },
                "errors": {},
            }
        )

    def test_catalog_registers_metadata_references_and_verifies_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "state" / "catalog.sqlite3"
            artifact = root / "backup.json"
            backup = self.backup(timestamp="2026-07-18T10:00:00+0000")
            save_json(artifact, backup)

            with SQLiteSnapshotCatalog(database) as catalog:
                service = SnapshotService(catalog)
                snapshot = service.register_backup(backup, artifact)
                self.assertEqual(snapshot.customer_hint, "1234")
                self.assertEqual(snapshot.resource_count, 2)
                self.assertEqual(catalog.get_snapshot(snapshot.snapshot_id), snapshot)
                references = catalog.list_references(
                    snapshot_id=snapshot.snapshot_id,
                    resource_type="servers",
                )
                self.assertEqual(len(references), 1)
                self.assertEqual(references[0].field_path, "$.serverGroupId")
                self.assertEqual(references[0].target_resource_type, "server_groups")
                verified = service.verify_snapshot(snapshot.snapshot_id[:12], load_json_file)
                self.assertTrue(verified.verified)

            raw_database = database.read_bytes()
            self.assertNotIn(b"never-store-this-secret", raw_database)
            self.assertNotIn(b"customer-sensitive-1234", raw_database)
            self.assertNotIn(b"original", raw_database)
            if os.name == "posix":
                self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            connection = sqlite3.connect(database)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(version, CATALOG_SCHEMA_VERSION)

    def test_inventory_history_search_and_drift_use_stable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with SQLiteSnapshotCatalog(root / "catalog.sqlite3") as catalog:
                snapshots = SnapshotService(catalog)
                first_path = root / "first.json"
                second_path = root / "second.json"
                first = self.backup(timestamp="2026-07-18T10:00:00+0000")
                second = self.backup(
                    timestamp="2026-07-19T10:00:00+0000",
                    description="configuration-changed",
                )
                save_json(first_path, first)
                save_json(second_path, second)
                first_record = snapshots.register_backup(first, first_path)
                second_record = snapshots.register_backup(second, second_path)

                inventory = InventoryService(catalog)
                latest, matches = inventory.list_resources(
                    snapshot_identifier="latest",
                    search="inventory server",
                )
                self.assertEqual(latest.snapshot_id, second_record.snapshot_id)
                self.assertEqual([item.stable_key for item in matches], ["inventoryserver"])
                history = inventory.history(
                    resource_type="servers",
                    stable_key="inventoryserver",
                )
                self.assertEqual(len(history), 2)
                drift = inventory.drift(first_record.snapshot_id, "latest")
                self.assertTrue(drift.same_tenant)
                self.assertEqual(drift.summary["changed"], 1)
                self.assertEqual(drift.summary["unchanged"], 1)

    def test_snapshot_cli_import_and_inventory_do_not_require_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "backup.json"
            database = root / "catalog.sqlite3"
            audit = root / "http-audit.log"
            save_json(artifact, self.backup(timestamp="2026-07-19T10:00:00+0000"))
            env_backup = dict(os.environ)
            try:
                for key in list(os.environ):
                    if key.startswith("ZPA_SOURCE_") or key.startswith("ZPA_TARGET_"):
                        os.environ.pop(key)
                imported = main(
                    [
                        "--catalog",
                        str(database),
                        "--audit-log",
                        str(audit),
                        "--run-ledger",
                        str(root / "run-ledger.jsonl"),
                        "snapshot",
                        "import",
                        str(artifact),
                    ]
                )
                listed = main(
                    [
                        "--catalog",
                        str(database),
                        "--audit-log",
                        str(audit),
                        "--run-ledger",
                        str(root / "run-ledger.jsonl"),
                        "inventory",
                        "list",
                        "--format",
                        "json",
                    ]
                )
            finally:
                os.environ.clear()
                os.environ.update(env_backup)
            self.assertEqual(imported, 0)
            self.assertEqual(listed, 0)


if __name__ == "__main__":
    unittest.main()
