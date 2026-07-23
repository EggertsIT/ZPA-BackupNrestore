"""Catalog the high-impact Business Continuity delete call."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete",
    "DELETE",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="business-continuity-settings/delete-business-continuity-settings",
)
