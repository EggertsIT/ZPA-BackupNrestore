"""GET one Private Cloud Controller group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudControllerGroup/{id}",
    documentation_slug="private-cloud-controller-group/get-private-cloud-controller-group-by-id",
)
