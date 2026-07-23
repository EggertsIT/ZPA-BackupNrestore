"""Catalog the operational Private Cloud Controller delete call."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloudController/{id}",
    role="delete", high_impact=True, support="catalog-only",
    documentation_slug="private-cloud-controller/delete-private-cloud-controller",
    notes="Live controller deletion is intentionally excluded from generic restore.",
)
