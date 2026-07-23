"""GET one Cloud Connector group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/cloudConnectorGroup/{id}",
    documentation_slug="cloud-connector-groups/get-edge-connector-group",
)
