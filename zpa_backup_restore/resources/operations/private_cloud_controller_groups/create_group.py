"""Catalog Private Cloud Controller group creation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create",
    "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudControllerGroup",
    high_impact=True,
    support="catalog-only",
    documentation_slug="private-cloud-controller-group/create-private-cloud-controller-group",
    notes="Requires a resolved Private Cloud site association.",
)
