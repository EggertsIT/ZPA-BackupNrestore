"""Server API definition."""

from .model import ResourceSpec
from .operations.servers import OPERATIONS

SPEC = ResourceSpec(
    key="servers",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/server",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/server/{id}",
    operations=OPERATIONS,
)
