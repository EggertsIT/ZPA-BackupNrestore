"""Catalog the operational Private Cloud Controller update call."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudController/{id}",
    role="update", high_impact=True, support="catalog-only",
    documentation_slug="private-cloud-controller/update-private-cloud-controller",
    notes="Live controller mutation is intentionally excluded from generic restore.",
)
