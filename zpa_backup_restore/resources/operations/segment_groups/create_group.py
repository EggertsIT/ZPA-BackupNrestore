"""POST a Segment Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup",
    documentation_slug="segment-group-management/adds-a-new-segment-group-for-the-specified-customer",
)
