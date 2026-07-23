"""DELETE one Application Segment."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete",
    "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}",
    documentation_slug=(
        "application-segment-management/"
        "deletes-the-application-segment-for-the-specified-id"
    ),
)
