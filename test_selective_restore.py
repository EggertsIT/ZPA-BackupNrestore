import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore import cli
from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.core.integrity import attach_manifest, preflight_restore
from zpa_backup_restore.core.restore import apply_diff
from zpa_backup_restore.core.selection import (
    build_restore_scope,
    compute_restore_diff,
)
from zpa_backup_restore.core.simulation import simulate_restore
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.resources import RESOURCES
from zpa_backup_restore.services.assurance import (
    build_assured_simulation,
    fresh_destination_diff,
)
from zpa_backup_restore.storage.backups import save_json


class SelectiveRestoreTests(unittest.TestCase):
    def backup(self, customer_id: str, **resources: object) -> dict:
        payload = {key: [] for key in RESOURCES}
        payload.update(
            {
                "idps": [],
                "saml_attributes": [],
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
                    "timestamp": "2026-07-23T12:00:00+0000",
                    "customerId": customer_id,
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": payload,
                "errors": {},
                "warnings": [],
            }
        )

    @staticmethod
    def rule(
        rule_id: str,
        name: str,
        *,
        enabled: bool,
        order: int,
    ) -> dict:
        return {
            "id": rule_id,
            "name": name,
            "enabled": enabled,
            "ruleOrder": order,
            "policySetId": "source-policy",
            "_policySetId": "source-policy",
            "_policyTypeName": "ACCESS_POLICY",
        }

    def test_one_policy_rule_is_selected_by_policy_type_and_name(self) -> None:
        source = self.backup(
            "source-customer",
            policy_sets={
                "ACCESS_POLICY": {
                    "id": "source-policy",
                    "name": "ACCESS_POLICY",
                }
            },
            policy_rules=[
                self.rule("source-13", "Access Policy 13", enabled=True, order=1),
                self.rule("source-14", "Access Policy 14", enabled=True, order=2),
            ],
        )
        target = self.backup(
            "target-customer",
            policy_sets={
                "ACCESS_POLICY": {
                    "id": "target-policy",
                    "name": "ACCESS_POLICY",
                }
            },
            policy_rules=[
                self.rule("target-13", "Access Policy 13", enabled=False, order=2),
                self.rule("target-14", "Access Policy 14", enabled=False, order=1),
            ],
        )

        diff = compute_restore_diff(
            source,
            target,
            selectors=["policy_rules/ACCESS_POLICY/Access Policy 13"],
        )

        updates = diff["resources"]["policy_rules"]["to_update"]
        self.assertEqual([item["source"]["name"] for item in updates], ["Access Policy 13"])
        self.assertEqual(diff["resources"]["policy_rule_order"]["to_update"], [])
        self.assertEqual(
            diff["scope"]["resolvedSelectors"][0]["selector"],
            "policy_rules/ACCESS_POLICY:accesspolicy13",
        )

    def test_policy_order_is_explicit_for_a_selective_policy_restore(self) -> None:
        source = self.backup(
            "source-customer",
            policy_rules=[
                self.rule("source-a", "Rule A", enabled=True, order=1),
                self.rule("source-b", "Rule B", enabled=True, order=2),
            ],
        )
        target = self.backup(
            "target-customer",
            policy_rules=[
                self.rule("target-a", "Rule A", enabled=True, order=2),
                self.rule("target-b", "Rule B", enabled=True, order=1),
            ],
        )

        diff = compute_restore_diff(
            source,
            target,
            selectors=["policy_rules/ACCESS_POLICY/Rule A"],
            restore_policy_order=True,
        )

        self.assertEqual(diff["scope"]["policyOrder"], "restore")
        self.assertEqual(len(diff["resources"]["policy_rule_order"]["to_update"]), 1)

    def test_dependency_inclusion_is_explicit_and_recursive(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "source-server", "name": "Server A"}],
            server_groups=[
                {
                    "id": "source-group",
                    "name": "Group A",
                    "servers": [{"id": "source-server"}],
                }
            ],
        )
        target = self.backup("target-customer")

        selected_only = compute_restore_diff(
            source,
            target,
            selectors=["server_groups/groupa"],
        )
        blocked = simulate_restore(
            selected_only,
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )
        self.assertTrue(blocked["hasBlockingIssues"])
        self.assertEqual(blocked["operations"][0]["resource"], "server_groups")

        with_dependencies = compute_restore_diff(
            source,
            target,
            selectors=["server_groups/Group A"],
            include_dependencies=True,
        )
        simulation = simulate_restore(
            with_dependencies,
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )
        self.assertFalse(simulation["hasBlockingIssues"])
        self.assertEqual(
            [operation["resource"] for operation in simulation["operations"]],
            ["servers", "server_groups"],
        )
        reasons = {
            item["selector"]: item["reason"]
            for item in with_dependencies["scope"]["resolvedSelectors"]
        }
        self.assertEqual(reasons["servers/servera"], "dependency")

    def test_live_executor_receives_only_the_selected_change(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[
                {"id": "source-a", "name": "Server A", "enabled": True},
                {"id": "source-b", "name": "Server B", "enabled": True},
            ],
        )
        target = self.backup(
            "target-customer",
            servers=[
                {"id": "target-a", "name": "Server A", "enabled": False},
                {"id": "target-b", "name": "Server B", "enabled": False},
            ],
        )
        diff = compute_restore_diff(
            source,
            target,
            selectors=["servers/Server A"],
        )

        class RecordingClient:
            customer_id = "target-customer"

            def __init__(self) -> None:
                self.calls: list[tuple[str, str, dict | None]] = []

            def request(
                self,
                method: str,
                path: str,
                *,
                body: dict | None = None,
            ) -> dict:
                self.calls.append((method, path, body))
                return {}

        client = RecordingClient()
        result = apply_diff(
            client,
            diff,
            source,
            target,
            dry_run=False,
            allow_delete=False,
            allow_high_impact=False,
        )

        self.assertEqual(result["ok"], 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0], "PUT")
        self.assertTrue(client.calls[0][1].endswith("/server/target-a"))
        self.assertEqual(client.calls[0][2]["name"], "Server A")

    def test_whole_resource_scope_keeps_that_domain_only(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "source-server", "name": "Server A"}],
            segment_groups=[{"id": "source-segment", "name": "Segment A"}],
        )
        target = self.backup("target-customer")

        diff = compute_restore_diff(
            source,
            target,
            resource_types=["servers"],
        )

        self.assertEqual(diff["summary"]["servers"]["create"], 1)
        self.assertEqual(diff["summary"]["segment_groups"]["create"], 0)
        self.assertEqual(diff["scope"]["selectedResourceTypes"], ["servers"])

    def test_missing_and_ambiguous_selectors_block_planning(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[
                {"id": "one", "name": "Duplicate"},
                {"id": "two", "name": "Duplicate"},
            ],
        )
        with self.assertRaisesRegex(CliError, "was not found"):
            build_restore_scope(source, selectors=["servers/missing"])
        with self.assertRaisesRegex(CliError, "ambiguous"):
            build_restore_scope(source, selectors=["servers/duplicate"])

    def test_scoped_preflight_rejects_a_hand_edited_diff(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "source-server", "name": "Server A", "enabled": True}],
        )
        target = self.backup(
            "target-customer",
            servers=[{"id": "target-server", "name": "Server A", "enabled": False}],
        )
        diff = compute_restore_diff(
            source,
            target,
            selectors=["servers/Server A"],
        )
        diff["resources"]["servers"]["to_update"] = []

        issues = preflight_restore(source, target, diff)

        self.assertIn(
            "selective diff changes do not match its persisted scope and restore inputs",
            issues,
        )

    def test_scoped_assurance_ignores_unrelated_drift_but_blocks_selected_drift(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[
                {"id": "source-a", "name": "Server A", "enabled": True},
                {"id": "source-b", "name": "Server B", "enabled": True},
            ],
        )
        target = self.backup(
            "target-customer",
            servers=[
                {"id": "target-a", "name": "Server A", "enabled": False},
                {"id": "target-b", "name": "Server B", "enabled": False},
            ],
        )
        diff = compute_restore_diff(
            source,
            target,
            selectors=["servers/Server A"],
        )
        simulation = build_assured_simulation(
            diff,
            source,
            target,
            allow_delete=False,
            allow_high_impact=False,
        )
        unrelated_drift = self.backup(
            "target-customer",
            servers=[
                {"id": "target-a", "name": "Server A", "enabled": False},
                {"id": "target-b", "name": "Server B", "enabled": True},
            ],
        )

        fresh = fresh_destination_diff(
            simulation,
            source,
            unrelated_drift,
            allow_delete=False,
            allow_high_impact=False,
        )

        self.assertEqual(fresh["summary"]["servers"]["update"], 1)
        self.assertEqual(
            fresh["resources"]["servers"]["to_update"][0]["source"]["name"],
            "Server A",
        )

        selected_drift = self.backup(
            "target-customer",
            servers=[
                {"id": "target-a", "name": "Server A", "enabled": True},
                {"id": "target-b", "name": "Server B", "enabled": False},
            ],
        )
        with self.assertRaisesRegex(CliError, "Destination drift detected"):
            fresh_destination_diff(
                simulation,
                source,
                selected_drift,
                allow_delete=False,
                allow_high_impact=False,
            )

    def test_inventory_search_prints_a_copyable_restore_plan_command(self) -> None:
        backup = self.backup(
            "source-customer",
            servers=[{"id": "source-server", "name": "Server A"}],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_path = root / "source backup.json"
            catalog_path = root / "catalog.sqlite3"
            audit_path = root / "audit.log"
            ledger_path = root / "ledger.jsonl"
            save_json(backup_path, backup)
            common = [
                "--catalog",
                str(catalog_path),
                "--audit-log",
                str(audit_path),
                "--run-ledger",
                str(ledger_path),
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                imported = cli.main([*common, "snapshot", "import", str(backup_path)])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                searched = cli.main(
                    [
                        *common,
                        "inventory",
                        "search",
                        "Server A",
                        "--snapshot",
                        "latest",
                        "--restore-commands",
                    ]
                )

        self.assertEqual(imported, 0)
        self.assertEqual(searched, 0)
        self.assertIn("servers/servera", output.getvalue())
        self.assertIn("restore-plan --source-backup", output.getvalue())
        self.assertIn("source backup.json'", output.getvalue())

    def test_cli_diff_and_simulation_preserve_the_selected_scope(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[
                {"id": "source-a", "name": "Server A", "enabled": True},
                {"id": "source-b", "name": "Server B", "enabled": True},
            ],
        )
        target = self.backup(
            "target-customer",
            servers=[
                {"id": "target-a", "name": "Server A", "enabled": False},
                {"id": "target-b", "name": "Server B", "enabled": False},
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.json"
            target_path = root / "target.json"
            diff_path = root / "selected-diff.json"
            simulation_path = root / "selected-simulation.json"
            report_path = root / "selected-simulation.html"
            save_json(source_path, source)
            save_json(target_path, target)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                diff_result = cli.main(
                    [
                        "--audit-log",
                        str(root / "diff-audit.log"),
                        "--no-run-ledger",
                        "diff",
                        "--source-backup",
                        str(source_path),
                        "--target-backup",
                        str(target_path),
                        "--out",
                        str(diff_path),
                        "--select",
                        "servers/Server A",
                    ]
                )
                simulation_result = cli.main(
                    [
                        "--audit-log",
                        str(root / "simulation-audit.log"),
                        "--no-run-ledger",
                        "simulate",
                        "--source-backup",
                        str(source_path),
                        "--target-backup",
                        str(target_path),
                        "--diff",
                        str(diff_path),
                        "--out",
                        str(simulation_path),
                        "--report-out",
                        str(report_path),
                    ]
                )
            diff_document = json.loads(diff_path.read_text(encoding="utf-8"))
            simulation_document = json.loads(
                simulation_path.read_text(encoding="utf-8")
            )

        self.assertEqual(diff_result, 0)
        self.assertEqual(simulation_result, 0)
        self.assertEqual(diff_document["scope"]["mode"], "selected")
        self.assertEqual(diff_document["summary"]["servers"]["update"], 1)
        self.assertEqual(
            simulation_document["scope"]["resolvedSelectors"][0]["selector"],
            "servers/servera",
        )
        self.assertIn("reviewed restore command:", output.getvalue())

    def test_no_selection_preserves_complete_diff_behavior(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "source-server", "name": "Server A"}],
        )
        target = self.backup("target-customer")

        expected = compute_diff(source, target)
        actual = compute_restore_diff(source, target)

        self.assertNotIn("scope", actual)
        self.assertEqual(actual["resources"], expected["resources"])
        self.assertEqual(actual["summary"], expected["summary"])


if __name__ == "__main__":
    unittest.main()
