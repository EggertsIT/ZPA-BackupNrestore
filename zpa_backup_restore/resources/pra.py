"""Privileged Remote Access API definitions."""

from .model import ResourceSpec
from .operations.pra_consoles import OPERATIONS as CONSOLE_OPERATIONS
from .operations.pra_portals import OPERATIONS as PORTAL_OPERATIONS

PORTALS = ResourceSpec(
    key="pra_portals",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/praPortal",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/praPortal/{id}",
    operations=PORTAL_OPERATIONS,
    depends_on=("application_segments",),
)

CONSOLES = ResourceSpec(
    key="pra_consoles",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/praConsole",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/praConsole/{id}",
    operations=CONSOLE_OPERATIONS,
    depends_on=("pra_portals", "server_groups", "application_segments"),
)

SPECS = (PORTALS, CONSOLES)
