"""GET one LSS configuration."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig/{id}",
    documentation_slug="log-streaming-service-lss-configuration/gets-the-lss-configuration-details-for-the-specified-id",
)
