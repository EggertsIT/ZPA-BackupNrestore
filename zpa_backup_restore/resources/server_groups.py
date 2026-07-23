"""Server Group API definition."""

from .model import ResourceSpec
from .operations.server_groups import OPERATIONS

SPEC = ResourceSpec(
    key="server_groups",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/serverGroup/{id}",
    operations=OPERATIONS,
    depends_on=("servers", "app_connector_groups"),
)
