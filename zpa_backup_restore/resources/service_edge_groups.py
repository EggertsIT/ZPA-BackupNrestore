"""Service Edge Group API definition."""

from .model import ResourceSpec
from .operations.service_edge_groups import OPERATIONS

SPEC = ResourceSpec(
    key="service_edge_groups",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup/{id}",
    operations=OPERATIONS,
    skip_fields=frozenset({"serviceEdges"}),
    notes="Private Service Edge instances are not cloned; only group configuration is handled.",
)
