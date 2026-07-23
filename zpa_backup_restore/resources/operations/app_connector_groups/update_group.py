"""PUT one App Connector group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup/{id}",
    documentation_slug="app-connector-group-management/updates-the-app-connector-group-details-for-the-specified-id",
)
