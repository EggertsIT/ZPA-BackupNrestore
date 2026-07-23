"""GET all Browser Access groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/browserAccessGroup",
    pagination="page",
    documentation_slug="browser-access-group/get-browser-access-groups",
)
