"""GET all App Connector groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup",
    pagination="page",
    documentation_slug="app-connector-group/gets-all-configured-app-connector-groups-for-the-specified-customer",
)
