"""GET one Private Cloud site."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloud/{id}",
    documentation_slug="site/get-site-by-id",
)
