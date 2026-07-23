"""Catalog Emergency Access user creation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/user",
    support="catalog-only",
    documentation_slug="emergency-access-management/add-emergency-access-user",
    notes="Operational break-glass state is never generically restored.",
)
