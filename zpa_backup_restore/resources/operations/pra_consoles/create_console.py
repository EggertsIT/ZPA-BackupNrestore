"""POST a PRA Console."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/praConsole",
    documentation_slug="privileged-console-management/add-pra-console",
)
