"""Segment Group API definition."""

from .model import ResourceSpec
from .operations.segment_groups import OPERATIONS

SPEC = ResourceSpec(
    key="segment_groups",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup/{id}",
    operations=OPERATIONS,
)
