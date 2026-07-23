"""POST a Server Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup",
    documentation_slug="server-group-management/add-a-new-server-group",
)
