"""Catalog expired Privileged Approval cleanup."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete_expired", "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/approval/expired",
    role="special", support="catalog-only",
    documentation_slug="privileged-approval-management/delete-expired-privileged-approvals",
)
