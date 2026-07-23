"""Catalog Private Cloud site deletion."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete",
    "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/privateCloud/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="site/delete-site",
)
