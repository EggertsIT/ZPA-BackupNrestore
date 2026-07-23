"""GET all Application Segments."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/application",
    pagination="page",
    documentation_slug=(
        "application-segment-management/"
        "gets-all-configured-application-segments-for-the-specified-customer"
    ),
)
