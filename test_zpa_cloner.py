import unittest

from zpa_cloner import (
    IDMapper,
    apply_diff,
    compute_diff,
    diff_action_totals,
    effective_policy_types,
    expected_detail_skip,
    policy_types_for_restore_source,
    seed_identity_refs,
    status_label,
)
from zpa_integrity import attach_manifest, preflight_restore, validate_backup
from zpa_policy_tool import CliError
from zpa_report import render_report
from zpa_resources import POLICY_TYPES, migration_order_issues


class ZpaClonerTests(unittest.TestCase):
    def minimal_backup(self, customer_id: str = "123") -> dict:
        return attach_manifest(
            {
                "meta": {
                    "label": "tenant",
                    "timestamp": "2026-06-02T10:00:00+0000",
                    "customerId": customer_id,
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
                    "servers": [],
                    "server_groups": [],
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

    def minimal_diff(self, source_id: str = "123", target_id: str = "456") -> dict:
        def empty() -> dict:
            return {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}

        return {
            "meta": {
                "source": {"customerId": source_id},
                "target": {"customerId": target_id},
            },
            "resources": {
                "microtenants": empty(),
                "inspection_custom_controls": empty(),
                "inspection_profiles": empty(),
                "cbi_profiles": empty(),
                "app_connector_groups": empty(),
                "service_edge_groups": empty(),
                "segment_groups": empty(),
                "servers": empty(),
                "server_groups": empty(),
                "application_segments": empty(),
                "lss_configs": empty(),
                "pra_portals": empty(),
                "pra_consoles": empty(),
                "policy_rules": empty(),
            },
        }

    def test_migration_order_satisfies_declared_dependencies(self) -> None:
        self.assertEqual(migration_order_issues(), [])

    def test_manifest_validates_and_detects_tampering(self) -> None:
        backup = self.minimal_backup()

        self.assertEqual(validate_backup(backup, strict=True), [])

        backup["resources"]["servers"].append({"id": "server-1", "name": "Server"})
        issues = validate_backup(backup, strict=True)

        self.assertIn("manifest sha256 does not match backup contents", issues)

    def test_preflight_detects_customer_id_mismatch(self) -> None:
        source = self.minimal_backup("source")
        target = self.minimal_backup("target")
        diff = self.minimal_diff("wrong-source", "target")

        issues = preflight_restore(source, target, diff)

        self.assertIn("diff source customerId does not match source backup", issues)

    def test_restore_plan_uses_policy_types_from_backup(self) -> None:
        source = self.minimal_backup("source")
        source["meta"]["policyTypes"] = ["ACCESS_POLICY", "TIMEOUT_POLICY"]

        policy_types = policy_types_for_restore_source(source, ["INSPECTION_POLICY"])

        self.assertEqual(policy_types, ["ACCESS_POLICY", "TIMEOUT_POLICY"])

    def test_restore_plan_falls_back_to_selected_policy_types(self) -> None:
        source = self.minimal_backup("source")
        source["meta"].pop("policyTypes")

        policy_types = policy_types_for_restore_source(source, ["INSPECTION_POLICY"])

        self.assertEqual(policy_types, ["INSPECTION_POLICY"])

    def test_cloner_defaults_to_all_policy_rule_types(self) -> None:
        self.assertEqual(effective_policy_types([]), POLICY_TYPES)

    def test_expected_detail_skip_handles_default_microtenant_not_found(self) -> None:
        error = CliError("resource.not.found: No resource exists with the given id/name :0")

        self.assertTrue(expected_detail_skip("microtenants", "0", error))
        self.assertFalse(expected_detail_skip("microtenants", "1", error))
        self.assertFalse(expected_detail_skip("servers", "0", error))

    def test_diff_action_totals_summarizes_changes(self) -> None:
        diff = self.minimal_diff()
        diff["resources"]["servers"]["to_create"] = [{"name": "Server"}]
        diff["resources"]["server_groups"]["to_update"] = [{"source": {}, "target": {}}]
        diff["resources"]["application_segments"]["to_delete"] = [{"name": "App"}]

        self.assertEqual(diff_action_totals(diff), {"create": 1, "update": 1, "delete": 1})

    def test_status_label_expands_operator_terms(self) -> None:
        self.assertEqual(status_label("dry"), "DRY-RUN")
        self.assertEqual(status_label("ok"), "OK")
        self.assertEqual(status_label("skip"), "SKIP")
        self.assertEqual(status_label("error"), "ERROR")

    def test_compute_diff_matches_policy_rules_by_policy_type_and_name(self) -> None:
        source = {
            "meta": {"label": "source"},
            "resources": {
                "app_connector_groups": [],
                "service_edge_groups": [],
                "segment_groups": [],
                "servers": [],
                "server_groups": [],
                "application_segments": [],
                "policy_rules": [
                    {"id": "1", "_policyTypeName": "ACCESS_POLICY", "name": "LAB-Zugriff", "action": "ALLOW"},
                ],
            },
        }
        target = {
            "meta": {"label": "target"},
            "resources": {
                "app_connector_groups": [],
                "service_edge_groups": [],
                "segment_groups": [],
                "servers": [],
                "server_groups": [],
                "application_segments": [],
                "policy_rules": [
                    {"id": "2", "_policyTypeName": "ACCESS_POLICY", "name": "LAB-Zugriff", "action": "DENY"},
                ],
            },
        }

        diff = compute_diff(source, target)

        self.assertEqual(diff["summary"]["policy_rules"]["update"], 1)
        self.assertEqual(diff["resources"]["policy_rules"]["to_update"][0]["target"]["id"], "2")

    def test_diff_ignores_tenant_specific_ids(self) -> None:
        source = {
            "meta": {"label": "source"},
            "resources": {
                "app_connector_groups": [{"id": "src-group", "name": "Connectors"}],
                "service_edge_groups": [],
                "segment_groups": [],
                "servers": [],
                "server_groups": [],
                "application_segments": [],
                "policy_rules": [
                    {
                        "id": "src-rule",
                        "_policyTypeName": "ACCESS_POLICY",
                        "policySetId": "src-policy-set",
                        "name": "LAB-Zugriff",
                        "action": "ALLOW",
                    },
                ],
            },
        }
        target = {
            "meta": {"label": "target"},
            "resources": {
                "app_connector_groups": [{"id": "tgt-group", "name": "Connectors"}],
                "service_edge_groups": [],
                "segment_groups": [],
                "servers": [],
                "server_groups": [],
                "application_segments": [],
                "policy_rules": [
                    {
                        "id": "tgt-rule",
                        "_policyTypeName": "ACCESS_POLICY",
                        "policySetId": "tgt-policy-set",
                        "name": "LAB-Zugriff",
                        "action": "ALLOW",
                    },
                ],
            },
        }

        diff = compute_diff(source, target)

        self.assertEqual(diff["summary"]["app_connector_groups"]["update"], 0)
        self.assertEqual(diff["summary"]["policy_rules"]["update"], 0)
        self.assertEqual(diff["summary"]["policy_rules"]["unchanged"], 1)

    def test_identity_mapper_remaps_scim_group_and_attribute_entry_values(self) -> None:
        source = {
            "resources": {
                "idps": [{"id": "src-idp", "name": "AzureAD"}],
                "scim_attributes": [{"id": "src-attr", "name": "Username", "_idpName": "AzureAD"}],
                "scim_groups": [{"id": "src-scim-group", "displayName": "Lab Users", "_idpName": "AzureAD"}],
            },
        }
        target = {
            "resources": {
                "idps": [{"id": "tgt-idp", "name": "AzureAD"}],
                "scim_attributes": [{"id": "tgt-attr", "name": "Username", "_idpName": "AzureAD"}],
                "scim_groups": [{"id": "tgt-scim-group", "displayName": "Lab Users", "_idpName": "AzureAD"}],
            },
        }
        mapper = IDMapper()
        seed_identity_refs(mapper, source, target)
        rule = {
            "conditions": [
                {
                    "operands": [
                        {
                            "objectType": "SCIM_GROUP",
                            "entryValues": [{"lhs": "src-attr", "rhs": "src-scim-group"}],
                            "idpId": "src-idp",
                        },
                        {
                            "objectType": "SCIM",
                            "entryValues": [{"lhs": "src-attr", "rhs": "user@example.com"}],
                            "idpId": "src-idp",
                        },
                    ],
                },
            ],
        }

        remapped = mapper.remap(rule)

        self.assertEqual(remapped["conditions"][0]["operands"][0]["entryValues"][0]["lhs"], "tgt-attr")
        self.assertEqual(remapped["conditions"][0]["operands"][0]["entryValues"][0]["rhs"], "tgt-scim-group")
        self.assertEqual(remapped["conditions"][0]["operands"][1]["entryValues"][0]["lhs"], "tgt-attr")
        self.assertEqual(remapped["conditions"][0]["operands"][1]["entryValues"][0]["rhs"], "user@example.com")
        self.assertEqual(remapped["conditions"][0]["operands"][1]["idpId"], "tgt-idp")

    def test_identity_mapper_remaps_read_only_reference_inventory_by_name(self) -> None:
        source = {
            "resources": {
                "idps": [],
                "scim_attributes": [],
                "scim_groups": [],
                "posture_profiles": [{"id": "src-posture", "name": "Disk Encryption"}],
                "trusted_networks": [{"id": "src-network", "name": "Office"}],
            },
        }
        target = {
            "resources": {
                "idps": [],
                "scim_attributes": [],
                "scim_groups": [],
                "posture_profiles": [{"id": "tgt-posture", "name": "Disk Encryption"}],
                "trusted_networks": [{"id": "tgt-network", "name": "Office"}],
            },
        }
        mapper = IDMapper()
        seed_identity_refs(mapper, source, target)

        remapped = mapper.remap(
            {
                "conditions": [
                    {
                        "operands": [
                            {"entryValues": [{"lhs": "postureProfileId", "rhs": "src-posture"}]},
                            {"entryValues": [{"lhs": "trustedNetworkId", "rhs": "src-network"}]},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(remapped["conditions"][0]["operands"][0]["entryValues"][0]["rhs"], "tgt-posture")
        self.assertEqual(remapped["conditions"][0]["operands"][1]["entryValues"][0]["rhs"], "tgt-network")

    def test_report_redacts_sensitive_values(self) -> None:
        diff = {
            "summary": {
                "app_connector_groups": {"create": 1, "update": 0, "delete": 0, "unchanged": 0},
                "service_edge_groups": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
                "segment_groups": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
                "servers": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
                "server_groups": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
                "application_segments": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
                "policy_rules": {"create": 0, "update": 0, "delete": 0, "unchanged": 0},
            },
            "resources": {
                "app_connector_groups": {
                    "to_create": [{"id": "1", "name": "Group", "clientSecret": "dont-print"}],
                    "to_update": [],
                    "to_delete": [],
                    "unchanged": [],
                },
                "service_edge_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "segment_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "servers": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "server_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "application_segments": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "policy_rules": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
            },
        }

        html = render_report(title="Test", diff=diff, include_coverage=False)

        self.assertIn("[REDACTED]", html)
        self.assertNotIn("dont-print", html)

    def test_apply_skips_high_impact_without_extra_flag(self) -> None:
        backup = {
            "resources": {
                "microtenants": [],
                "idps": [],
                "scim_attributes": [],
                "scim_groups": [],
            },
        }
        diff = {
            "resources": {
                "microtenants": {
                    "to_create": [{"id": "src-mt", "name": "Tenant A"}],
                    "to_update": [],
                    "to_delete": [],
                    "unchanged": [],
                },
                "inspection_custom_controls": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "inspection_profiles": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "cbi_profiles": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "app_connector_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "service_edge_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "segment_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "servers": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "server_groups": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "application_segments": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "lss_configs": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "pra_portals": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "pra_consoles": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
                "policy_rules": {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []},
            },
        }

        result = apply_diff(
            None,
            diff,
            backup,
            backup,
            dry_run=False,
            allow_delete=False,
            allow_high_impact=False,
        )

        self.assertEqual(result["skipped"], 1)
        self.assertIn("high-impact", result["log"][0]["detail"])

    def test_apply_deletes_dependents_before_dependencies(self) -> None:
        class RecordingClient:
            customer_id = "target"

            def __init__(self) -> None:
                self.calls = []

            def request(self, method, path, query=None, body=None):
                self.calls.append((method, path))
                return {}

        source = self.minimal_backup("source")
        target = self.minimal_backup("target")
        diff = self.minimal_diff("source", "target")
        diff["resources"]["servers"]["to_delete"] = [{"id": "server-1", "name": "Server"}]
        diff["resources"]["server_groups"]["to_delete"] = [{"id": "server-group-1", "name": "Server Group"}]
        client = RecordingClient()

        apply_diff(
            client,
            diff,
            source,
            target,
            dry_run=False,
            allow_delete=True,
            allow_high_impact=True,
        )

        delete_paths = [path for method, path in client.calls if method == "DELETE"]
        server_group_delete = next(index for index, path in enumerate(delete_paths) if "/serverGroup/" in path)
        server_delete = next(index for index, path in enumerate(delete_paths) if "/server/" in path)
        self.assertLess(server_group_delete, server_delete)


if __name__ == "__main__":
    unittest.main()
