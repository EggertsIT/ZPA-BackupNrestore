"""DELETE one LSS configuration."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig/{id}",
    documentation_slug="log-streaming-service-lss-configuration/deletes-the-lss-configuration-for-the-specified-id",
)
