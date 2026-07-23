"""PUT one policy rule at a new evaluation order."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "reorder",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/policySet/{policy_set_id}/rule/{rule_id}/reorder/{rule_order}",
    role="special",
    documentation_slug="policy-management/updates-the-rule-order-for-the-specified-id",
)
