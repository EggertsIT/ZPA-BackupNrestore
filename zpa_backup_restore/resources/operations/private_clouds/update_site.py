"""Catalog Private Cloud site update."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloud/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="site/update-site",
    notes="Requires two-phase site/controller-group association planning.",
)
