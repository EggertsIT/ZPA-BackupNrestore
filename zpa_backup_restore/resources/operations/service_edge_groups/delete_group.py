"""DELETE one Private Service Edge group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup/{id}",
    documentation_slug="private-service-edge-group-management/delete-private-broker-group",
)
