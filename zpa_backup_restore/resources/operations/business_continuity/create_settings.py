"""Catalog the high-impact Business Continuity create call."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create",
    "POST",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings",
    high_impact=True,
    support="catalog-only",
    documentation_slug="business-continuity-settings/create-business-continuity-settings",
    notes="Disabled until a credential and private-key injection workflow exists.",
)
