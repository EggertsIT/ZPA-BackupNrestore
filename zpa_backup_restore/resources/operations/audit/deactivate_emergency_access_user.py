"""Catalog Emergency Access user deactivation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "deactivate", "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/user/{id}/deactivate",
    role="special", high_impact=True, support="catalog-only",
    documentation_slug="emergency-access-management/deactivate-emergency-access-user",
)
