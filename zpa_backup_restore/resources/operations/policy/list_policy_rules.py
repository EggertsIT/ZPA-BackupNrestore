"""GET all rules for a policy type."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/policySet/rules/policyType/{policy_type}",
    pagination="page",
    documentation_slug="policy-management/gets-paginated-policy-rules-for-the-specified-policy-type",
)
