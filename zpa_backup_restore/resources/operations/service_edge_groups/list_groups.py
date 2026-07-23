"""GET all Private Service Edge groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup",
    pagination="page",
    documentation_slug="service-edge-group/get-private-broker-groups",
)
