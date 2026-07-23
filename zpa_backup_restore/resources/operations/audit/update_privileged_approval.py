"""Catalog Privileged Approval update."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/approval/{id}",
    support="catalog-only",
    documentation_slug="privileged-approval-management/update-privileged-approval",
)
