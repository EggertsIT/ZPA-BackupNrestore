"""POST one Application Segment."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create",
    "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application",
    documentation_slug=(
        "application-segment-management/"
        "adds-a-new-application-segment-for-the-specified-customer"
    ),
)
