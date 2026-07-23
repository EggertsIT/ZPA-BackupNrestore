"""GET all Private Cloud sites."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloud",
    pagination="page",
    documentation_slug="site/get-all-sites",
)
