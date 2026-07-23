import json
import os
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore.cli import main
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.repositories.jsonl_audit_ledger import JsonlRunAuditLedger
from zpa_backup_restore.services.audits import AuditService


class AuditLedgerTests(unittest.TestCase):
    def test_hash_chain_redaction_queries_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "run-ledger.jsonl"
            ledger = JsonlRunAuditLedger(path, clock=lambda: "2026-07-19T12:00:00Z")
            ledger.append(
                run_id="run-success",
                event_type="run.started",
                data={"command": "snapshot.import", "clientSecret": "must-not-appear"},
            )
            ledger.append(
                run_id="run-success",
                event_type="artifact.recorded",
                data={"role": "output.backup", "sha256": "abc", "bytes": 42},
            )
            ledger.append(
                run_id="run-success",
                event_type="run.finished",
                data={"exitCode": 0, "error": ""},
            )
            ledger.append(
                run_id="run-failure",
                event_type="run.started",
                data={"command": "restore"},
            )
            ledger.append(
                run_id="run-failure",
                event_type="run.finished",
                data={"exitCode": 1, "error": "password=do-not-store"},
            )

            verification = ledger.verify()
            self.assertTrue(verification.valid, verification.errors)
            self.assertEqual(verification.event_count, 5)
            self.assertEqual(verification.run_count, 2)
            self.assertNotIn("must-not-appear", path.read_text(encoding="utf-8"))
            self.assertNotIn("do-not-store", path.read_text(encoding="utf-8"))
            self.assertTrue(path.with_name(path.name + ".head").is_file())
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            service = AuditService(ledger)
            failures = service.list_runs(failures_only=True)
            self.assertEqual([run["runId"] for run in failures], ["run-failure"])
            summary = {row["command"]: row for row in service.command_summary()}
            self.assertEqual(summary["restore"]["failed"], 1)
            self.assertEqual(summary["snapshot.import"]["succeeded"], 1)
            detail = service.run_detail("run-succ")
            self.assertEqual(detail["summary"]["artifactCount"], 1)

    def test_modification_and_tail_truncation_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "run-ledger.jsonl"
            ledger = JsonlRunAuditLedger(path)
            ledger.append(run_id="run-1", event_type="run.started", data={"command": "backup"})
            ledger.append(run_id="run-1", event_type="run.finished", data={"exitCode": 0})

            lines = path.read_text(encoding="utf-8").splitlines()
            modified = json.loads(lines[0])
            modified["data"]["command"] = "restore"
            lines[0] = json.dumps(modified, sort_keys=True, separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertFalse(ledger.verify().valid)
            with self.assertRaises(CliError):
                ledger.append(run_id="run-2", event_type="run.started", data={"command": "diff"})

            # Restore the valid first event only; the separate checkpoint exposes tail removal.
            original_ledger = JsonlRunAuditLedger(Path(temp_dir) / "second-ledger.jsonl")
            original_ledger.append(run_id="run-1", event_type="run.started", data={"command": "backup"})
            original_ledger.append(run_id="run-1", event_type="run.finished", data={"exitCode": 0})
            valid_lines = original_ledger.path.read_text(encoding="utf-8").splitlines()
            original_ledger.path.write_text(valid_lines[0] + "\n", encoding="utf-8")
            result = original_ledger.verify()
            self.assertFalse(result.valid)
            self.assertIn("ledger event count does not match head checkpoint", result.errors)

    def test_audit_verify_cli_is_credential_free(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "run-ledger.jsonl"
            ledger = JsonlRunAuditLedger(path)
            ledger.append(run_id="run-1", event_type="run.started", data={"command": "inventory.list"})
            ledger.append(run_id="run-1", event_type="run.finished", data={"exitCode": 0})
            result = main(
                [
                    "--run-ledger",
                    str(path),
                    "--audit-log",
                    str(root / "http-audit.log"),
                    "audit",
                    "verify",
                ]
            )
            self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
