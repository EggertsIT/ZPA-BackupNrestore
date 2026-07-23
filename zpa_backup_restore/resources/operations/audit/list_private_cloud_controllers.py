"""GET all live Private Cloud Controllers."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudController",
    pagination="page",
    documentation_slug="private-cloud-controller/get-all-private-cloud-controllers",
)
