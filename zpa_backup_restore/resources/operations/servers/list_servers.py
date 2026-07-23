"""GET all Application Servers."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/server",
    pagination="page",
    documentation_slug="server-management/gets-all-configured-servers-for-the-specified-customer",
)
