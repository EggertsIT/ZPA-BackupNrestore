"""DELETE one Application Server."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/server/{id}",
    documentation_slug="server-management/deletes-the-server-for-the-specified-id",
)
