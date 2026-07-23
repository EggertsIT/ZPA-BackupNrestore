"""Catalog Private Cloud site creation."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create",
    "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloud",
    high_impact=True,
    support="catalog-only",
    documentation_slug="site/create-site",
    notes="Requires two-phase site/controller-group association planning.",
)
