"""GET one Application Segment."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}",
    documentation_slug=(
        "application-segment-management/"
        "gets-the-application-segment-details-for-the-specified-id"
    ),
)
