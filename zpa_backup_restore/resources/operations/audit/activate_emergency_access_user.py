"""Catalog Emergency Access user activation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "activate", "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/user/{id}/activate",
    role="special", high_impact=True, support="catalog-only",
    documentation_slug="emergency-access-management/activate-emergency-access-user",
)
