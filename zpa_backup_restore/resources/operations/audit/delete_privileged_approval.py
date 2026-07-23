"""Catalog Privileged Approval deletion."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/approval/{id}",
    support="catalog-only",
    documentation_slug="privileged-approval-management/delete-privileged-approval",
)
