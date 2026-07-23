"""GET one Private Service Edge group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup/{id}",
    documentation_slug="private-service-edge-group-management/get-private-broker-group",
)
