"""GET one Emergency Access user."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/emergencyAccess/user/{id}",
    documentation_slug="emergency-access-management/get-emergency-access-user",
)
