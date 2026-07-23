"""GET one PRA Console."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/praConsole/{id}",
    documentation_slug="privileged-console-management/get-pra-console",
)
