"""DELETE one Microtenant."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/microtenants/{id}",
    high_impact=True,
)
