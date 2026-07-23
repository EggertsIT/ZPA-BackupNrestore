"""GET all Emergency Access users."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/users",
    pagination="cursor",
    documentation_slug="emergency-access-management/get-all-emergency-access-group-users",
)
