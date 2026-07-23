"""GET one Server Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup/{id}",
    documentation_slug="server-group-management/gets-the-server-group-details-for-the-specified-id",
)
