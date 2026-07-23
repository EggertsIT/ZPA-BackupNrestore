"""PUT one Server Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup/{id}",
    documentation_slug="server-group-management/updates-the-server-group-for-the-specified-id",
)
