"""PUT the complete ordered rule-ID list for a policy set."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "bulk_reorder",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/policySet/{policy_set_id}/reorder",
    role="special",
    documentation_slug=(
        "policy-management/"
        "bulk-reorders-all-the-rules-in-a-policy-set-execute-this-api-only-once-to-reorder-the-rules"
    ),
)
