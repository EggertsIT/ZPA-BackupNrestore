"""Catalog the high-impact Business Continuity update call."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update",
    "PUT",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings/{id}",
    high_impact=True,
    support="catalog-only",
    documentation_slug="business-continuity-settings/update-business-continuity-settings",
    notes="Disabled because sanitized snapshots intentionally omit key material.",
)
