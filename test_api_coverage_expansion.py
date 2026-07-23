import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from zpa_backup_restore.cli import main
from zpa_backup_restore.core.backup import detail_items, get_identity_refs, list_cursor
from zpa_backup_restore.core.diff import compute_diff
from zpa_backup_restore.core.mapping import IDMapper, seed_identity_refs
from zpa_backup_restore.core.restore import apply_application_segment_special, apply_diff
from zpa_backup_restore.core.simulation import simulate_restore
from zpa_backup_restore.resources.application_segments import special_operation_sections
from zpa_backup_restore.resources.registry import COVERAGE_RESOURCES, MIGRATION_ORDER, RESOURCES


def empty_section() -> dict:
    return {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}


def special_diff(sections: dict) -> dict:
    resources = {key: empty_section() for key in MIGRATION_ORDER}
    resources.update(sections)
    return {"meta": {}, "resources": resources, "summary": {}}


class FakeClient:
    customer_id = "target-customer"

    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, *, query=None, body=None):
        self.calls.append((method, path, query, body))
        return {}


class IdentityClient:
    customer_id = "source-customer"

    def idps(self):
        return [{"id": "source-idp", "name": "Corporate IdP"}]

    def scim_attributes(self, idp_id):
        return [{"id": "source-scim", "name": "department"}]

    def request(self, method, path, *, query=None, body=None):
        if "/samlAttribute/idp/" in path:
            return {"list": [{"id": "source-saml", "name": "email"}], "totalPages": 1}
        if "/scimgroup/idpId/" in path:
            return {"list": [{"id": "source-group", "name": "Engineering"}], "totalPages": 1}
        raise AssertionError(path)


class ApiCoverageExpansionTests(unittest.TestCase):
    def test_all_modeled_domains_use_explicit_operations(self) -> None:
        self.assertTrue(COVERAGE_RESOURCES)
        self.assertEqual(
            [key for key, meta in COVERAGE_RESOURCES.items() if meta["operation_source"] != "explicit"],
            [],
        )
        self.assertGreaterEqual(
            sum(len(meta["operations"]) for meta in COVERAGE_RESOURCES.values()),
            136,
        )
        self.assertEqual(
            RESOURCES["browser_access_groups"]["path"],
            "/mgmtconfig/v1/admin/customers/{customer_id}/browserAccessGroup",
        )

    def test_audit_mutations_are_cataloged_but_never_enabled(self) -> None:
        for key in (
            "business_continuity_settings",
            "private_clouds",
            "private_cloud_controller_groups",
            "private_cloud_controllers",
            "emergency_access_users",
            "privileged_approvals",
        ):
            meta = RESOURCES[key]
            self.assertFalse(meta["writable"])
            self.assertEqual(meta["mode"], "audit")
            for operation in meta["operations"]:
                if operation["method"] != "GET":
                    self.assertEqual(operation["support"], "catalog-only")

    def test_identity_backup_and_scoped_saml_mapping(self) -> None:
        refs = get_identity_refs(IdentityClient(), warnings=[], log_level="normal")
        self.assertEqual(refs["saml_attributes"][0]["_idpName"], "Corporate IdP")
        source = {"resources": refs}
        target = {
            "resources": {
                "idps": [{"id": "target-idp", "name": "Corporate IdP"}],
                "saml_attributes": [
                    {
                        "id": "target-saml",
                        "name": "email",
                        "_idpName": "Corporate IdP",
                    }
                ],
                "scim_attributes": [],
                "scim_groups": [],
            }
        }
        mapper = IDMapper()
        seed_identity_refs(mapper, source, target)
        self.assertEqual(mapper.lookup("source-saml"), "target-saml")

    def test_cursor_pagination_and_sensitive_backup_stripping(self) -> None:
        class CursorClient:
            customer_id = "customer"

            def request(self, method, path, *, query=None, body=None):
                if query.get("pageId") == "next":
                    return {"list": [{"userId": "2"}]}
                return {"list": [{"userId": "1"}], "nextPage": "next"}

        self.assertEqual(
            [item["userId"] for item in list_cursor(CursorClient(), "/users")],
            ["1", "2"],
        )

        class ReferenceClient:
            customer_id = "customer"

            def request(self, method, path, *, query=None, body=None):
                if path.endswith("getAltClouds"):
                    return ["zscaler.net", "zscalertwo.net"]
                return [
                    {
                        "id": "cert",
                        "name": "Connector",
                        "privateKey": "never-store",
                        "nested": {"certificateBody": "never-store"},
                    }
                ]

        clouds = detail_items(
            ReferenceClient(),
            "zscaler_clouds",
            RESOURCES["zscaler_clouds"],
            warnings=[],
            log_level="normal",
        )
        certificates = detail_items(
            ReferenceClient(),
            "enrollment_certificates",
            RESOURCES["enrollment_certificates"],
            warnings=[],
            log_level="normal",
        )
        self.assertEqual(clouds[0], {"id": "zscaler.net", "name": "zscaler.net"})
        self.assertNotIn("privateKey", certificates[0])
        self.assertNotIn("certificateBody", certificates[0]["nested"])

    def test_policy_reorder_is_planned_and_executed_with_target_ids(self) -> None:
        source = {
            "meta": {"customerId": "source"},
            "resources": {
                "policy_sets": {"ACCESS_POLICY": {"id": "source-set"}},
                "policy_rules": [
                    {"id": "source-a", "name": "A", "ruleOrder": 1, "_policyTypeName": "ACCESS_POLICY"},
                    {"id": "source-b", "name": "B", "ruleOrder": 2, "_policyTypeName": "ACCESS_POLICY"},
                ],
            },
        }
        target = {
            "meta": {"customerId": "target-customer"},
            "resources": {
                "policy_sets": {"ACCESS_POLICY": {"id": "target-set"}},
                "policy_rules": [
                    {"id": "target-b", "name": "B", "ruleOrder": 1, "_policyTypeName": "ACCESS_POLICY"},
                    {"id": "target-a", "name": "A", "ruleOrder": 2, "_policyTypeName": "ACCESS_POLICY"},
                ],
            },
        }
        diff = compute_diff(source, target)
        simulation = simulate_restore(
            diff, source, target, allow_delete=False, allow_high_impact=False
        )
        reorder = next(item for item in simulation["operations"] if item["action"] == "REORDER")
        self.assertEqual(reorder["request"]["body"], ["target-a", "target-b"])

        client = FakeClient()
        result = apply_diff(
            client,
            diff,
            source,
            target,
            dry_run=False,
            allow_delete=False,
            allow_high_impact=False,
        )
        self.assertEqual(result["errors"], 0)
        self.assertIn(
            (
                "PUT",
                "/mgmtconfig/v1/admin/customers/target-customer/policySet/target-set/reorder",
                None,
                ["target-a", "target-b"],
            ),
            client.calls,
        )

    def test_application_move_and_share_are_high_impact_special_operations(self) -> None:
        source_app = {
            "id": "source-app",
            "name": "ERP",
            "microtenantId": "source-child",
            "microtenantName": "Child",
            "segmentGroupId": "source-segment-group",
            "serverGroups": [{"id": "source-server-group", "name": "ERP Servers"}],
            "sharedMicrotenantDetails": {
                "sharedToMicrotenants": [{"id": "source-share", "name": "Shared Child"}]
            },
        }
        target_app = {
            "id": "target-app",
            "name": "ERP",
            "microtenantId": "0",
            "microtenantName": "Default",
            "segmentGroupId": "target-segment-group",
            "serverGroups": [{"id": "target-server-group", "name": "ERP Servers"}],
            "sharedMicrotenantDetails": {"sharedToMicrotenants": []},
        }
        sections = special_operation_sections([source_app], [target_app])
        diff = special_diff(sections)
        source = {
            "meta": {"customerId": "source"},
            "resources": {
                "microtenants": [
                    {"id": "source-child", "name": "Child"},
                    {"id": "source-share", "name": "Shared Child"},
                ],
                "segment_groups": [{"id": "source-segment-group", "name": "ERP Segment"}],
                "server_groups": [{"id": "source-server-group", "name": "ERP Servers"}],
                "application_segments": [source_app],
            },
        }
        target = {
            "meta": {"customerId": "target-customer"},
            "resources": {
                "microtenants": [
                    {"id": "target-child", "name": "Child"},
                    {"id": "target-share", "name": "Shared Child"},
                ],
                "segment_groups": [{"id": "target-segment-group", "name": "ERP Segment"}],
                "server_groups": [{"id": "target-server-group", "name": "ERP Servers"}],
                "application_segments": [target_app],
            },
        }
        blocked_by_safeguard = simulate_restore(
            diff, source, target, allow_delete=False, allow_high_impact=False
        )
        self.assertEqual(
            {item["status"] for item in blocked_by_safeguard["operations"]},
            {"skipped"},
        )
        simulation = simulate_restore(
            diff, source, target, allow_delete=False, allow_high_impact=True
        )
        move, share = simulation["operations"]
        self.assertEqual(move["request"]["method"], "POST")
        self.assertEqual(move["request"]["body"]["targetMicrotenantId"], "target-child")
        self.assertEqual(share["request"]["method"], "PUT")
        self.assertEqual(share["request"]["body"]["shareToMicrotenants"], ["target-share"])

        mapper = IDMapper()
        mapper.map.update(
            {
                "source-child": "target-child",
                "source-segment-group": "target-segment-group",
                "source-server-group": "target-server-group",
                "source-share": "target-share",
            }
        )
        client = FakeClient()
        apply_application_segment_special(
            client,
            "application_segment_moves",
            sections["application_segment_moves"]["to_update"][0],
            mapper,
        )
        self.assertEqual(client.calls[0][0:2], (
            "POST",
            "/mgmtconfig/v1/admin/customers/target-customer/application/target-app/move",
        ))

    def test_new_child_microtenant_application_uses_deferred_move(self) -> None:
        source_app = {
            "id": "source-app",
            "name": "New ERP",
            "microtenantId": "source-child",
            "microtenantName": "Child",
            "segmentGroupId": "source-segment-group",
            "serverGroups": [{"id": "source-server-group", "name": "ERP Servers"}],
            "sharedMicrotenantDetails": {"sharedToMicrotenants": []},
        }
        sections = special_operation_sections([source_app], [])
        diff = special_diff(sections)
        diff["resources"]["application_segments"]["to_create"] = [source_app]
        source = {
            "meta": {"customerId": "source"},
            "resources": {
                "microtenants": [{"id": "source-child", "name": "Child"}],
                "segment_groups": [{"id": "source-segment-group", "name": "ERP Segment"}],
                "server_groups": [{"id": "source-server-group", "name": "ERP Servers"}],
                "application_segments": [source_app],
            },
        }
        target = {
            "meta": {"customerId": "target-customer"},
            "resources": {
                "microtenants": [{"id": "target-child", "name": "Child"}],
                "segment_groups": [{"id": "target-segment-group", "name": "ERP Segment"}],
                "server_groups": [{"id": "target-server-group", "name": "ERP Servers"}],
                "application_segments": [],
            },
        }
        simulation = simulate_restore(
            diff, source, target, allow_delete=False, allow_high_impact=True
        )
        move = next(item for item in simulation["operations"] if item["action"] == "MOVE")
        self.assertEqual(move["status"], "planned")
        self.assertIn("$planned:application_segments:source-app", move["request"]["path"])
        self.assertEqual(move["payloadStatus"], "deferred")

    def test_coverage_json_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "--no-run-ledger",
                        "--no-api-progress",
                        "--audit-log",
                        str(Path(temp_dir) / "audit.log"),
                        "coverage",
                        "--json",
                    ]
                )
            rows = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(all(row["operation_source"] == "explicit" for row in rows))
        self.assertIn("audit log:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
