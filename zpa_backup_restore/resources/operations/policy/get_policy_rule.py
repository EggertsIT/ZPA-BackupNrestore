"""GET one Policy Rule."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET",
    "/mgmtconfig/v2/admin/customers/{customer_id}/policySet/{policy_set_id}/rule/{rule_id}",
    documentation_slug="policy-management/gets-the-rule-in-a-policy-for-the-specified-id",
)
