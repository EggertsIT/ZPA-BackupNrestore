"""PUT one Segment Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup/{id}",
    documentation_slug="segment-group-management/updates-the-segment-group-for-the-specified-id",
)
