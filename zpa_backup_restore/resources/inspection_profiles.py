"""Inspection profile API definition."""

from .model import ResourceSpec
from .operations.inspection_profiles import OPERATIONS

SPEC = ResourceSpec(
    key="inspection_profiles",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile/{id}",
    operations=OPERATIONS,
    depends_on=("inspection_custom_controls",),
)
