"""Catalog Private Cloud Controller group update."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudControllerGroup/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="private-cloud-controller-group/update-private-cloud-controller-group",
    notes="Requires a resolved Private Cloud site association.",
)
