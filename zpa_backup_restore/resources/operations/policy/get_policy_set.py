"""GET the Policy Set for a policy type."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get_policy_set", "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/policySet/policyType/{policy_type}",
    role="get_set",
    documentation_slug="policy-management/gets-the-policy-set-for-the-specified-policy-type",
)
