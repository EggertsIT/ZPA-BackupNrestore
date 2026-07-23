"""POST an Application Server."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/server",
    documentation_slug="server-management/adds-a-new-server-for-the-specified-customer",
)
