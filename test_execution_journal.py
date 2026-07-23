import json
import os
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.core.integrity import attach_manifest
from zpa_backup_restore.core.restore import apply_diff
from zpa_backup_restore.resources import RESOURCES
from zpa_backup_restore.services.execution_journal import FileExecutionJournal


class FakeClient:
    customer_id = "target-customer"

    def request(self, method, path, *, query=None, body=None):
        return {"id": "created-target-id"}


class ExecutionJournalTests(unittest.TestCase):
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
                    "label": "tenant",
                    "timestamp": "2026-07-19T10:00:00+0000",
                    "customerId": customer_id,
                    "policyTypes": ["ACCESS_POLICY"],
                },
                "resources": payload,
                "errors": {},
                "warnings": [],
            }
        )

    def test_apply_persists_each_operation_and_created_target_id(self) -> None:
        source = self.backup(
            "source-customer",
            servers=[{"id": "source-server-id", "name": "Server A"}],
        )
        target = self.backup("target-customer")
        diff = compute_diff(source, target)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "execution-journal.json"
            scope = {
                "schemaVersion": "1.0",
                "mode": "selected",
                "requestedSelectors": ["servers/servera"],
                "selectedResourceTypes": [],
                "resolvedSelectors": [
                    {
                        "resourceType": "servers",
                        "stableKey": "servera",
                        "displayName": "Server A",
                        "reason": "selected",
                        "selector": "servers/servera",
                    }
                ],
                "referencedResources": [],
                "includeDependencies": False,
                "policyOrder": "preserve-target",
            }
            journal = FileExecutionJournal(
                path,
                run_id="run-1",
                plan_sha256="a" * 64,
                scope=scope,
            )
            result = apply_diff(
                FakeClient(),
                diff,
                source,
                target,
                dry_run=False,
                allow_delete=False,
                allow_high_impact=False,
                journal=journal,
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            operations = list(document["operations"].values())
            self.assertEqual(result["ok"], 1)
            self.assertEqual(len(operations), 1)
            self.assertEqual(operations[0]["status"], "ok")
            self.assertEqual(operations[0]["sourceId"], "source-server-id")
            self.assertEqual(operations[0]["createdTargetId"], "created-target-id")
            self.assertEqual(document["planSha256"], "a" * 64)
            self.assertEqual(
                document["scope"]["resolvedSelectors"][0]["selector"],
                "servers/servera",
            )
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
