"""GET all Private Cloud Controller groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudControllerGroup",
    pagination="page",
    documentation_slug="private-cloud-controller-group/get-all-private-cloud-controller-groups",
)
