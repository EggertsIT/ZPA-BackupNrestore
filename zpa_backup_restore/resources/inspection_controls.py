"""Inspection custom-control API definition."""

from .model import ResourceSpec
from .operations.inspection_controls import OPERATIONS

SPEC = ResourceSpec(
    key="inspection_custom_controls",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom/{id}",
    operations=OPERATIONS,
    notes="Custom inspection controls. Predefined controls are not cloned.",
)
