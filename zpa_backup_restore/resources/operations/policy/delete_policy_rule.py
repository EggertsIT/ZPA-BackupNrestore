"""DELETE one Policy Rule."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/policySet/{policy_set_id}/rule/{rule_id}",
    documentation_slug="policy-management/deletes-the-rule-in-a-policy-for-the-specified-id",
)
