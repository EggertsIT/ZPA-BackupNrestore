import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore.cli import main
from zpa_backup_restore.core.catalog import MIGRATION_ORDER
from zpa_backup_restore.core.integrity import attach_manifest
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.reporting.disaster_recovery import (
    render_disaster_recovery_report,
)
from zpa_backup_restore.repositories.jsonl_audit_ledger import JsonlRunAuditLedger
from zpa_backup_restore.services.disaster_recovery import (
    KNOWN_EXTERNAL_RECOVERY_AREAS,
    build_disaster_recovery_runbook,
    load_disaster_recovery_runbook,
    save_disaster_recovery_runbook,
    update_disaster_recovery_checklist,
    verify_disaster_recovery_runbook,
)
from zpa_backup_restore.storage.backups import save_backup_json, save_json


class DisasterRecoveryRunbookTests(unittest.TestCase):
    def backup(self, *, endpoint_error: bool = False) -> dict:
        resources = {resource_type: [] for resource_type in MIGRATION_ORDER}
        resources.update(
            {
                "server_groups": [
                    {
                        "id": "group-1",
                        "name": "Recovery Server Group",
                    }
                ],
                "servers": [
                    {
                        "id": "server-1",
                        "name": "Recovery Server",
                        "serverGroupId": "group-1",
                        "clientSecret": "must-not-enter-the-runbook",
                    }
                ],
                "policy_sets": {
                    "ACCESS_POLICY": {
                        "id": "policy-set-1",
                        "name": "Access Policy",
                        "policyType": "ACCESS_POLICY",
                    }
                },
                "policy_rules": [
                    {
                        "id": "rule-1",
                        "name": "Recovery Access Rule",
                        "policyType": "ACCESS_POLICY",
                        "policySetId": "policy-set-1",
                    }
                ],
                "idps": [{"id": "idp-1", "name": "Corporate IdP"}],
                "saml_attributes": [],
                "scim_attributes": [],
                "scim_groups": [],
                "posture_profiles": [
                    {"id": "posture-1", "name": "Managed Device"}
                ],
                "business_continuity_settings": [
                    {
                        "id": "bc-1",
                        "name": "Primary Business Continuity",
                    }
                ],
            }
        )
        return attach_manifest(
            {
                "meta": {
                    "label": "production",
                    "timestamp": "2026-07-23T20:00:00+0000",
                    "customerId": "customer-sensitive-1234",
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": resources,
                "errors": (
                    {"private_clouds": "sanitized endpoint failure"}
                    if endpoint_error
                    else {}
                ),
                "warnings": [],
            }
        )

    def build(self, root: Path, *, endpoint_error: bool = False) -> tuple[Path, dict]:
        backup_path = root / "source.json"
        backup = self.backup(endpoint_error=endpoint_error)
        save_json(backup_path, backup)
        runbook = build_disaster_recovery_runbook(
            backup,
            backup_path,
            clock=lambda: "2026-07-23T20:30:00+0000",
        )
        return backup_path, runbook

    def test_runbook_covers_every_setting_domain_and_known_external_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path, runbook = self.build(Path(temp_dir))

            settings = {
                (item["resourceType"], item["name"]): item
                for item in runbook["items"]
                if item["category"] == "setting"
            }
            domains = {
                item["resourceType"]
                for item in runbook["items"]
                if item["category"] == "domain"
            }
            external = [
                item
                for item in runbook["items"]
                if item["category"] == "external-gap"
            ]

            self.assertIn(("servers", "Recovery Server"), settings)
            self.assertIn(("policy_rules", "Recovery Access Rule"), settings)
            self.assertIn(("posture_profiles", "Managed Device"), settings)
            self.assertIn(
                ("business_continuity_settings", "Primary Business Continuity"),
                settings,
            )
            self.assertEqual(domains, set(entry["resource"] for entry in runbook["coverage"]["domains"]))
            self.assertEqual(len(external), len(KNOWN_EXTERNAL_RECOVERY_AREAS))
            self.assertEqual(runbook["source"]["artifactPath"], str(backup_path.resolve()))
            self.assertEqual(runbook["coverage"]["modeledDomainCount"], 30)
            self.assertEqual(runbook["coverage"]["explicitOperationCount"], 136)
            self.assertIn("not a claim", runbook["coverage"]["claim"])

            server = settings[("servers", "Recovery Server")]
            self.assertEqual(server["capability"], "automated")
            self.assertIn(
                "--select servers/recoveryserver",
                server["commands"][0]["command"],
            )
            self.assertIn("server_groups/recoveryservergroup", server["dependencies"])

            policy_set = settings[("policy_sets", "Access Policy")]
            posture = settings[("posture_profiles", "Managed Device")]
            continuity = settings[
                ("business_continuity_settings", "Primary Business Continuity")
            ]
            self.assertEqual(policy_set["capability"], "reference")
            self.assertEqual(posture["capability"], "reference")
            self.assertEqual(continuity["capability"], "protected-manual")
            self.assertFalse(policy_set["commands"])
            self.assertFalse(posture["commands"])
            self.assertFalse(continuity["commands"])
            self.assertNotIn(
                "must-not-enter-the-runbook",
                json.dumps(runbook),
            )

    def test_incomplete_backup_creates_visible_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _backup_path, runbook = self.build(
                Path(temp_dir),
                endpoint_error=True,
            )
            private_cloud = next(
                domain
                for domain in runbook["coverage"]["domains"]
                if domain["resource"] == "private_clouds"
            )
            blockers = [
                item
                for item in runbook["items"]
                if item["status"] == "blocked"
            ]

            self.assertEqual(private_cloud["captureStatus"], "failed")
            self.assertTrue(
                any(item["category"] == "backup-issue" for item in blockers)
            )
            self.assertEqual(
                next(
                    item
                    for item in blockers
                    if item["id"] == "readiness.backup-integrity"
                )["status"],
                "blocked",
            )

    def test_checklist_updates_require_evidence_and_form_a_verified_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backup_path, runbook = self.build(root)
            path = root / "runbook.json"
            save_disaster_recovery_runbook(path, runbook)

            with self.assertRaises(CliError):
                update_disaster_recovery_checklist(
                    runbook,
                    item_identifier="readiness.backup-integrity",
                    status="completed",
                    operator="operator@example.com",
                )

            item = update_disaster_recovery_checklist(
                runbook,
                item_identifier="readiness.backup-integrity",
                status="completed",
                operator="operator@example.com",
                evidence="INC-2042 / validation report",
                clock=lambda: "2026-07-23T21:00:00+0000",
            )
            self.assertEqual(item["status"], "completed")
            self.assertEqual(runbook["auditTrail"][0]["fromStatus"], "pending")
            self.assertTrue(
                verify_disaster_recovery_runbook(runbook)["valid"],
                verify_disaster_recovery_runbook(runbook)["errors"],
            )

            runbook["auditTrail"][0]["evidence"] = "modified"
            verification = verify_disaster_recovery_runbook(runbook)
            self.assertFalse(verification["valid"])
            self.assertIn("audit event 1: event hash mismatch", verification["errors"])

    def test_plan_and_state_tampering_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _backup_path, runbook = self.build(Path(temp_dir))
            runbook["items"][0]["name"] = "Changed plan"
            self.assertIn(
                "runbook plan SHA-256 mismatch",
                verify_disaster_recovery_runbook(runbook)["errors"],
            )

            _backup_path, runbook = self.build(Path(temp_dir))
            runbook["items"][0]["status"] = "completed"
            result = verify_disaster_recovery_runbook(runbook)
            self.assertIn(
                "readiness.backup-integrity: checklist state does not match audit trail",
                result["errors"],
            )
            self.assertIn(
                "runbook checklist state SHA-256 mismatch",
                result["errors"],
            )

    def test_printable_report_contains_steps_commands_status_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _backup_path, runbook = self.build(root)
            html = render_disaster_recovery_report(
                runbook,
                runbook_path=root / "runbook.json",
            )

            self.assertIn("Recovery Server", html)
            self.assertIn("Ordered recovery procedure", html)
            self.assertIn("--select servers/recoveryserver", html)
            self.assertIn("Coverage gap / external evidence required", html)
            self.assertIn("Record completion", html)
            self.assertIn(runbook["integrity"]["planSha256"], html)
            self.assertNotIn("must-not-enter-the-runbook", html)
            self.assertIn("@media print", html)

    def test_cli_generate_check_status_report_and_verify_are_credential_free(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_path = root / "source.json"
            runbook_path = root / "runbook.json"
            report_path = root / "runbook.html"
            regenerated_path = root / "regenerated.html"
            audit_path = root / "http-audit.log"
            ledger_path = root / "run-ledger.jsonl"
            save_json(backup_path, self.backup())
            original_env = dict(os.environ)
            try:
                for key in list(os.environ):
                    if key.startswith("ZPA_SOURCE_") or key.startswith("ZPA_TARGET_"):
                        os.environ.pop(key)
                common = [
                    "--audit-log",
                    str(audit_path),
                    "--run-ledger",
                    str(ledger_path),
                ]
                generated = main(
                    [
                        *common,
                        "dr",
                        "generate",
                        "--source-backup",
                        str(backup_path),
                        "--out",
                        str(runbook_path),
                        "--report-out",
                        str(report_path),
                    ]
                )
                checked = main(
                    [
                        *common,
                        "dr",
                        "check",
                        "--runbook",
                        str(runbook_path),
                        "--item",
                        "readiness.backup-integrity",
                        "--status",
                        "completed",
                        "--actor",
                        "recovery-operator",
                        "--evidence",
                        "INC-2042",
                    ]
                )
                status = main(
                    [
                        *common,
                        "dr",
                        "status",
                        "--runbook",
                        str(runbook_path),
                        "--status",
                        "completed",
                        "--format",
                        "json",
                    ]
                )
                verified = main(
                    [
                        *common,
                        "dr",
                        "verify",
                        "--runbook",
                        str(runbook_path),
                    ]
                )
                reported = main(
                    [
                        *common,
                        "dr",
                        "report",
                        "--runbook",
                        str(runbook_path),
                        "--out",
                        str(regenerated_path),
                    ]
                )
            finally:
                os.environ.clear()
                os.environ.update(original_env)

            self.assertEqual(
                (generated, checked, status, verified, reported),
                (0, 0, 0, 0, 0),
            )
            self.assertTrue(report_path.is_file())
            self.assertTrue(regenerated_path.is_file())
            runbook = load_disaster_recovery_runbook(runbook_path)
            self.assertEqual(
                next(
                    item
                    for item in runbook["items"]
                    if item["id"] == "readiness.backup-integrity"
                )["status"],
                "completed",
            )
            self.assertTrue(verify_disaster_recovery_runbook(runbook)["valid"])
            self.assertTrue(JsonlRunAuditLedger(ledger_path).verify().valid)
            if os.name == "posix":
                self.assertEqual(runbook_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
    def test_cli_generates_runbook_from_encrypted_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_path = root / "source.json.enc"
            runbook_path = root / "encrypted-runbook.json"
            env_name = "ZPA_DR_TEST_PASSPHRASE"
            old_value = os.environ.get(env_name)
            os.environ[env_name] = "runbook-test-passphrase"
            try:
                save_backup_json(
                    backup_path,
                    self.backup(),
                    encrypted=True,
                    passphrase_env=env_name,
                )
                result = main(
                    [
                        "--backup-passphrase-env",
                        env_name,
                        "--audit-log",
                        str(root / "http-audit.log"),
                        "--run-ledger",
                        str(root / "run-ledger.jsonl"),
                        "dr",
                        "generate",
                        "--source-backup",
                        str(backup_path),
                        "--out",
                        str(runbook_path),
                    ]
                )
            finally:
                if old_value is None:
                    os.environ.pop(env_name, None)
                else:
                    os.environ[env_name] = old_value

            self.assertEqual(result, 0)
            runbook = load_disaster_recovery_runbook(runbook_path)
            self.assertTrue(runbook["source"]["encrypted"])
            server = next(
                item
                for item in runbook["items"]
                if item["resourceType"] == "servers"
                and item["name"] == "Recovery Server"
            )
            self.assertIn("--backup-passphrase-env", server["commands"][0]["command"])


if __name__ == "__main__":
    unittest.main()
