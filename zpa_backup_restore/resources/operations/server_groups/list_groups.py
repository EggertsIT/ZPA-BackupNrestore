"""GET all Server Groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup",
    pagination="page",
    documentation_slug="server-group-management/gets-all-configured-server-groups-for-the-specified-customer",
)
