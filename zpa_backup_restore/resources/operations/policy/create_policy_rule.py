"""POST a Policy Rule."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST",
    "/mgmtconfig/v2/admin/customers/{customer_id}/policySet/{policy_set_id}/rule",
    documentation_slug="policy-management/adds-a-new-policy-rule-for-the-specified-policy-set",
)
