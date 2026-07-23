"""Catalog Privileged Approval creation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/approval",
    support="catalog-only",
    documentation_slug="privileged-approval-management/add-privileged-approval",
)
