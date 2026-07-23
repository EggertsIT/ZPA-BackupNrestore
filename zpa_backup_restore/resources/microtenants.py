"""Microtenant API definition."""

from .model import ResourceSpec
from .operations.microtenants import OPERATIONS

SPEC = ResourceSpec(
    key="microtenants",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/microtenants",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/microtenants/{id}",
    operations=OPERATIONS,
    notes="High-impact tenant partitioning object. Review carefully before applying across tenants.",
    high_impact=True,
)
