"""GET one live Private Cloud Controller."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudController/{id}",
    documentation_slug="private-cloud-controller/get-private-cloud-controller-by-id",
)
