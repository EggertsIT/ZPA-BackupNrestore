"""Log Streaming Service configuration API definition."""

from .model import ResourceSpec
from .operations.lss_configs import OPERATIONS

SPEC = ResourceSpec(
    key="lss_configs",
    path="/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig",
    detail_path="/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig/{id}",
    operations=OPERATIONS,
    depends_on=("app_connector_groups", "service_edge_groups"),
    notes="Receiver and network reachability must be validated manually.",
)
