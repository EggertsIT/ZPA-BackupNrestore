"""GET one Segment Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup/{id}",
    documentation_slug="segment-group-management/gets-the-segment-group-details-for-the-specified-id",
)
