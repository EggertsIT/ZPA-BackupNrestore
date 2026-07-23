"""GET all configured Privileged Approvals."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/approval",
    pagination="page",
    documentation_slug=(
        "privileged-approval-management/"
        "gets-all-configured-privileged-approvals-for-the-specified-customer"
    ),
)
