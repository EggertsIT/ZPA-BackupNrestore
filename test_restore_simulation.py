import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from zpa_backup_restore import cli
from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.core.integrity import attach_manifest
from zpa_backup_restore.core.simulation import DEFERRED_REFERENCE_PREFIX, simulate_restore
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources import RESOURCES
from zpa_backup_restore.storage.backups import save_json


class RestoreSimulationTests(unittest.TestCase):
    def backup(self, customer_id: str, **resources: object) -> dict:
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
                    "timestamp": "2026-07-19T12:00:00+0000",
                    "customerId": customer_id,
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": payload,
                "errors": {},
                "warnings": [],
            }
        )

    def test_created_dependency_uses_deferred_reference_in_ordered_payload(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "server-source", "name": "Server A", "enabled": True}],
            server_groups=[
                {
                    "id": "group-source",
                    "name": "Group A",
                    "servers": [{"id": "server-source"}],
                }
            ],
        )
        target = self.backup("target-customer")

        simulation = simulate_restore(
            compute_diff(source, target),
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )

        server, group = simulation["operations"]
        self.assertEqual((server["resource"], group["resource"]), ("servers", "server_groups"))
        self.assertEqual(server["request"]["method"], "POST")
        self.assertNotIn("id", server["request"]["body"])
        reference = group["request"]["body"]["servers"][0]["id"]
        self.assertEqual(reference, f"{DEFERRED_REFERENCE_PREFIX}servers:server-source")
        self.assertEqual(group["payloadStatus"], "deferred")
        self.assertEqual(group["deferredReferences"][0]["path"], "$.servers[0].id")
        self.assertFalse(simulation["hasBlockingIssues"])

    def test_unmapped_read_only_reference_blocks_operation_with_field_path(self) -> None:
        source = self.backup(
            "source-customer",
            machine_groups=[{"id": "machine-source", "name": "Source Only"}],
            application_segments=[
                {
                    "id": "app-source",
                    "name": "App A",
                    "machineGroups": [{"id": "machine-source"}],
                }
            ],
        )
        target = self.backup("target-customer")

        simulation = simulate_restore(
            compute_diff(source, target),
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )

        operation = simulation["operations"][0]
        self.assertEqual(operation["status"], "blocked")
        self.assertEqual(
            operation["unresolvedReferences"],
            [{"path": "$.machineGroups[0].id", "sourceId": "machine-source"}],
        )
        self.assertTrue(simulation["hasBlockingIssues"])
        self.assertEqual(simulation["summary"]["unresolvedReferences"], 1)

    def test_safeguards_group_skipped_operations_by_reason(self) -> None:
        source = self.backup(
            "source-customer",
            microtenants=[{"id": "micro-source", "name": "Tenant A"}],
        )
        target = self.backup(
            "target-customer",
            servers=[{"id": "server-target", "name": "Delete Me"}],
        )

        simulation = simulate_restore(
            compute_diff(source, target),
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )

        self.assertEqual(simulation["summary"]["skipped"], 2)
        self.assertEqual(
            simulation["skipReasons"],
            {"deletes disabled": 1, "high-impact writes disabled": 1},
        )
        self.assertEqual(
            [operation["status"] for operation in simulation["operations"]],
            ["skipped", "skipped"],
        )

    def test_missing_target_id_blocks_update(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "server-source", "name": "Server A", "enabled": True}],
        )
        target = self.backup(
            "target-customer",
            servers=[{"name": "Server A", "enabled": False}],
        )

        simulation = simulate_restore(
            compute_diff(source, target),
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )

        self.assertEqual(simulation["operations"][0]["status"], "blocked")
        self.assertEqual(simulation["operations"][0]["reason"], "target servers ID is missing")

    def test_simulation_artifact_redacts_sensitive_payload_fields(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[
                {
                    "id": "server-source",
                    "name": "Server A",
                    "clientSecret": "must-not-persist",
                }
            ],
        )
        target = self.backup("target-customer")

        simulation = simulate_restore(
            compute_diff(source, target),
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )

        serialized = json.dumps(simulation)
        self.assertNotIn("must-not-persist", serialized)
        self.assertEqual(
            simulation["operations"][0]["request"]["body"]["clientSecret"],
            "[REDACTED]",
        )

    def test_simulate_cli_is_credential_free_and_writes_json_and_html(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "server-source", "name": "Server A"}],
        )
        target = self.backup("target-customer")
        diff = compute_diff(source, target)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.json"
            target_path = root / "target.json"
            diff_path = root / "diff.json"
            output_path = root / "simulation.json"
            report_path = root / "simulation.html"
            audit_path = root / "audit.log"
            save_json(source_path, source)
            save_json(target_path, target)
            save_json(diff_path, diff)

            clean_env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("ZPA_") and not key.startswith("ZSCALER_")
            }
            with mock.patch.dict(os.environ, clean_env, clear=True):
                result = cli.main(
                    [
                        "--audit-log",
                        str(audit_path),
                        "--run-ledger",
                        str(root / "run-ledger.jsonl"),
                        "simulate",
                        "--source-backup",
                        str(source_path),
                        "--target-backup",
                        str(target_path),
                        "--diff",
                        str(diff_path),
                        "--out",
                        str(output_path),
                        "--report-out",
                        str(report_path),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue(output_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertIn("Restore Simulation", report_path.read_text(encoding="utf-8"))
            self.assertIn("Ordered plan SHA-256", report_path.read_text(encoding="utf-8"))

    def test_restore_dry_run_is_a_simulate_alias(self) -> None:
        args = mock.Mock(dry_run=True)
        with mock.patch.object(cli, "command_simulate") as command_simulate:
            cli.command_apply(args)
        command_simulate.assert_called_once_with(args)

    def test_live_restore_refuses_blocked_simulation_before_loading_credentials(self) -> None:
        source = self.backup(
            "source-customer",
            machine_groups=[{"id": "machine-source", "name": "Source Only"}],
            application_segments=[
                {
                    "id": "app-source",
                    "name": "App A",
                    "machineGroups": [{"id": "machine-source"}],
                }
            ],
        )
        target = self.backup("target-customer")
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
                with self.assertRaisesRegex(CliError, "blocked operation"):
                    cli.command_apply(args)

            profile_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
