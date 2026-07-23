"""GET one Microtenant."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/microtenants/{id}",
)
