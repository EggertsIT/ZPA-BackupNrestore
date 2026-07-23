import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zpa_backup_restore import cli
from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.core.integrity import attach_manifest
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources import RESOURCES
from zpa_backup_restore.services.assurance import (
    build_assured_simulation,
    fresh_destination_diff,
    plan_sha256,
    validate_reviewed_simulation,
)
from zpa_backup_restore.storage.backups import save_json


class RestoreAssuranceTests(unittest.TestCase):
    def backup(self, customer_id: str, timestamp: str, **resources: object) -> dict:
        payload = {key: [] for key in RESOURCES}
        payload.update(
            {
                "idps": [],
                "scim_attributes": [],
                "scim_groups": [],
                "policy_sets": {},
                "policy_rules": [],
            }
        )
        payload.update(resources)
        return attach_manifest(
            {
                "meta": {
                    "label": "source" if customer_id == "source-customer" else "target",
                    "timestamp": timestamp,
                    "customerId": customer_id,
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": payload,
                "errors": {},
                "warnings": [],
            }
        )

    def restore_set(self) -> tuple[dict, dict, dict, dict]:
        source = self.backup(
            "source-customer",
            "2026-07-19T10:00:00+0000",
            servers=[{"id": "source-server", "name": "Server A", "enabled": True}],
        )
        target = self.backup(
            "target-customer",
            "2026-07-19T10:00:00+0000",
            servers=[{"id": "target-server", "name": "Server A", "enabled": False}],
        )
        diff = compute_diff(source, target)
        simulation = build_assured_simulation(
            diff,
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )
        return source, target, diff, simulation

    def test_assurance_binds_inputs_safeguards_and_complete_ordered_plan(self) -> None:
        source, target, diff, simulation = self.restore_set()
        assurance = simulation["assurance"]
        self.assertEqual(len(assurance["sourceBackupSha256"]), 64)
        self.assertEqual(len(assurance["targetBackupSha256"]), 64)
        self.assertEqual(len(assurance["diffSha256"]), 64)
        self.assertEqual(len(assurance["targetStateSha256"]), 64)
        self.assertEqual(assurance["planSha256"], plan_sha256(simulation))
        changed_timestamp = dict(simulation)
        changed_timestamp["timestamp"] = "later"
        self.assertEqual(plan_sha256(changed_timestamp), assurance["planSha256"])

        validate_reviewed_simulation(
            simulation,
            source,
            target,
            diff,
            allow_delete=False,
            allow_high_impact=False,
        )

        tampered = {**simulation, "operations": [dict(item) for item in simulation["operations"]]}
        tampered["operations"][0]["request"] = dict(tampered["operations"][0]["request"])
        tampered["operations"][0]["request"]["path"] = "/tampered"
        with self.assertRaisesRegex(CliError, "plan SHA-256"):
            validate_reviewed_simulation(
                tampered,
                source,
                target,
                diff,
                allow_delete=False,
                allow_high_impact=False,
            )
        with self.assertRaisesRegex(CliError, "delete safeguard"):
            validate_reviewed_simulation(
                simulation,
                source,
                target,
                diff,
                allow_delete=True,
                allow_high_impact=False,
            )

    def test_fresh_destination_blocks_configuration_and_object_id_drift(self) -> None:
        source, target, _diff, simulation = self.restore_set()
        same_state = self.backup(
            "target-customer",
            "2026-07-19T10:05:00+0000",
            servers=[{"id": "target-server", "name": "Server A", "enabled": False}],
        )
        fresh = fresh_destination_diff(
            simulation,
            source,
            same_state,
            allow_delete=False,
            allow_high_impact=False,
        )
        self.assertEqual(fresh["summary"]["servers"]["update"], 1)

        changed_config = self.backup(
            "target-customer",
            "2026-07-19T10:05:00+0000",
            servers=[{"id": "target-server", "name": "Server A", "enabled": True}],
        )
        with self.assertRaisesRegex(CliError, "Destination drift detected"):
            fresh_destination_diff(
                simulation,
                source,
                changed_config,
                allow_delete=False,
                allow_high_impact=False,
            )

        changed_id = self.backup(
            "target-customer",
            "2026-07-19T10:05:00+0000",
            servers=[{"id": "replacement-target-id", "name": "Server A", "enabled": False}],
        )
        with self.assertRaisesRegex(CliError, "different ordered plan"):
            fresh_destination_diff(
                simulation,
                source,
                changed_id,
                allow_delete=False,
                allow_high_impact=False,
            )

    def test_live_restore_requires_reviewed_simulation_before_credentials(self) -> None:
        source = self.backup(
            "source-customer",
            "2026-07-19T10:00:00+0000",
            servers=[{"id": "source-server", "name": "Server A"}],
        )
        target = self.backup("target-customer", "2026-07-19T10:00:00+0000")
        diff = compute_diff(source, target)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.json"
            target_path = root / "target.json"
            diff_path = root / "diff.json"
            save_json(source_path, source)
            save_json(target_path, target)
            save_json(diff_path, diff)
            args = argparse.Namespace(
                source_backup=str(source_path),
                target_backup=str(target_path),
                diff=str(diff_path),
                simulation=None,
                allow_unreviewed_plan=False,
                backup_passphrase_env="ZPA_BACKUP_PASSPHRASE",
                openssl_bin="openssl",
                allow_failed_backups=False,
                ignore_preflight=False,
                allow_delete=False,
                allow_high_impact=False,
                dry_run=False,
                yes=True,
                command="restore",
            )
            with mock.patch.object(cli, "profile_client") as profile_client:
                with self.assertRaisesRegex(CliError, "requires --simulation"):
                    cli.command_apply(args)
            profile_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
