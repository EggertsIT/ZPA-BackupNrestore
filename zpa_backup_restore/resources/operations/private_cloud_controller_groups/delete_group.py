"""Catalog Private Cloud Controller group deletion."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete",
    "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudControllerGroup/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="private-cloud-controller-group/delete-private-cloud-controller-group",
)
