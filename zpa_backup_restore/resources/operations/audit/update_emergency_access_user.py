"""Catalog Emergency Access user update."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/user/{id}",
    support="catalog-only",
    documentation_slug="emergency-access-management/update-emergency-access-user",
)
