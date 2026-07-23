"""GET all Cloud Connector groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/cloudConnectorGroup",
    pagination="page",
    documentation_slug="cloud-connector-groups/get-edge-connector-groups",
)
