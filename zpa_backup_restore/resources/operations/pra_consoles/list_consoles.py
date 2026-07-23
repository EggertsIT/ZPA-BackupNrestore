"""GET all PRA Consoles."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/praConsole",
    pagination="page",
    documentation_slug="privileged-console-management/gets-all-configured-privileged-consoles-for-the-specified-customer",
)
