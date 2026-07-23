"""DELETE one PRA Console."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/praConsole/{id}",
    documentation_slug="privileged-console-management/delete-pra-console",
)
