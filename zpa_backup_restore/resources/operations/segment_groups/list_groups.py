"""GET all Segment Groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/segmentGroup",
    pagination="page",
    documentation_slug="segment-group-management/gets-all-configured-segment-groups-for-the-specified-customer",
)
