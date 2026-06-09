import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from zpa_policy_tool import (
    ApiAuditLogger,
    DEFAULT_LEGACY_ZPA_BASE_URL,
    DEFAULT_ONEAPI_BASE_URL,
    ZscalerClient,
    add_scim_condition,
)


class AddScimConditionTests(unittest.TestCase):
    def test_legacy_client_uses_legacy_zpa_base_url(self) -> None:
        client = ZscalerClient(
            client_id="id",
            client_secret="secret",
            customer_id="customer",
            auth_mode="legacy",
        )

        self.assertEqual(client.zpa_base_url, DEFAULT_LEGACY_ZPA_BASE_URL)

    def test_oneapi_client_uses_oneapi_zpa_base_url(self) -> None:
        client = ZscalerClient(
            client_id="id",
            client_secret="secret",
            customer_id="customer",
            auth_mode="oneapi",
            zidentity_base_url="https://zidentity.example",
        )

        self.assertEqual(client.zpa_base_url, f"{DEFAULT_ONEAPI_BASE_URL}/zpa")

    def test_audit_logger_records_progress_and_redacts_sensitive_query_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "audit.log"
            logger = ApiAuditLogger(path, progress=True)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                request_id, started_at, display = logger.begin(
                    "GET",
                    "https://example.test/mgmtconfig/v1/admin/customers/123/application",
                    path="/mgmtconfig/v1/admin/customers/123/application",
                    query={"page": 1, "pagesize": 500, "client_secret": "do-not-log", "clientSecret": "also-redact"},
                )
                logger.finish(
                    request_id,
                    display,
                    started_at,
                    status=200,
                    headers={"x-request-id": "request-1"},
                    body={"totalPages": "1", "list": [{"id": "app-1", "name": "CRM"}]},
                    body_bytes=128,
                )

            output = stdout.getvalue()
            self.assertIn("api: GET /mgmtconfig/v1/admin/customers/123/application", output)
            self.assertNotIn("do-not-log", output)
            self.assertNotIn("also-redact", output)

            raw_log = path.read_text(encoding="utf-8")
            self.assertNotIn("do-not-log", raw_log)
            self.assertNotIn("also-redact", raw_log)
            records = [json.loads(line) for line in raw_log.splitlines()]

        self.assertEqual(records[0]["event"], "http.request.start")
        self.assertEqual(records[0]["query"]["client_secret"], "[REDACTED]")
        self.assertEqual(records[0]["query"]["clientSecret"], "[REDACTED]")
        self.assertEqual(records[1]["event"], "http.request.finish")
        self.assertEqual(records[1]["status"], 200)
        self.assertEqual(records[1]["response"]["record_count"], 1)
        self.assertEqual(records[1]["response_headers"]["x-request-id"], "request-1")

    def test_adds_scim_attribute_condition_to_scim_group_rule(self) -> None:
        rule = {
            "policySetId": "policy-set-1",
            "id": "rule-1",
            "conditions": [
                {
                    "operands": [
                        {
                            "objectType": "SCIM_GROUP",
                            "entryValues": [
                                {"lhs": "source-attribute-id", "rhs": "source-group-id"},
                            ],
                        },
                    ],
                    "operator": "OR",
                },
            ],
            "name": "LAB-Zugriff",
            "action": "ALLOW",
        }
        original = copy.deepcopy(rule)

        updated, status = add_scim_condition(
            rule,
            {"id": "idp-1", "name": "AzureAD"},
            {"id": "attribute-1", "name": "Username"},
            "user@example.com",
            "merge-same-attribute",
            "OR",
        )

        self.assertEqual(status, "added-condition")
        self.assertEqual(rule, original)
        self.assertEqual(updated["operator"], "AND")
        self.assertEqual(len(updated["conditions"]), 2)
        self.assertEqual(updated["conditions"][1]["operator"], "OR")
        self.assertEqual(
            updated["conditions"][1]["operands"],
            [
                {
                    "objectType": "SCIM",
                    "entryValues": [
                        {"lhs": "attribute-1", "rhs": "user@example.com"},
                    ],
                    "idpId": "idp-1",
                    "idpName": "AzureAD",
                },
            ],
        )

    def test_existing_scim_value_is_unchanged(self) -> None:
        rule = {
            "operator": "AND",
            "conditions": [
                {
                    "operator": "OR",
                    "operands": [
                        {
                            "objectType": "SCIM",
                            "entryValues": [
                                {"lhs": "attribute-1", "rhs": "user@example.com"},
                            ],
                            "idpId": "idp-1",
                        },
                    ],
                },
            ],
        }

        updated, status = add_scim_condition(
            rule,
            {"id": "idp-1", "name": "AzureAD"},
            {"id": "attribute-1", "name": "Username"},
            "user@example.com",
            "merge-same-attribute",
            "OR",
        )

        self.assertEqual(status, "unchanged")
        self.assertEqual(updated, rule)


if __name__ == "__main__":
    unittest.main()
