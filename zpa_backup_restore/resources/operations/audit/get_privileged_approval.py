"""GET one Privileged Approval."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/approval/{id}",
    documentation_slug="privileged-approval-management/get-privileged-approval",
)
