"""GET one Application Server."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/server/{id}",
    documentation_slug="server-management/gets-the-server-details-for-the-specified-id",
)
