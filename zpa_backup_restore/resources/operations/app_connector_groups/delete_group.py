"""DELETE one App Connector group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup/{id}",
    documentation_slug="app-connector-group-management/deletes-the-app-connector-group-for-the-specified-id",
)
