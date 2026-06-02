import copy
import unittest

from zpa_policy_tool import DEFAULT_LEGACY_ZPA_BASE_URL, DEFAULT_ONEAPI_BASE_URL, ZscalerClient, add_scim_condition


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
