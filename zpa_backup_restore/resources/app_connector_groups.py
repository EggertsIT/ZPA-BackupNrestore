"""App Connector Group API definition."""

from .model import ResourceSpec
from .operations.app_connector_groups import OPERATIONS

SPEC = ResourceSpec(
    key="app_connector_groups",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/appConnectorGroup/{id}",
    operations=OPERATIONS,
    skip_fields=frozenset({"connectors", "appConnectors"}),
    notes="App Connector instances are not cloned; only group configuration is handled.",
)
