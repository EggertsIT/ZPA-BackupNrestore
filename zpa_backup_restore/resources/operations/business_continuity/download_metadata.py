"""Catalog the Business Continuity SP metadata download."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "download_metadata",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings/metadata",
    role="export",
    support="excluded",
    documentation_slug="business-continuity-settings/download-sp-metadata",
    notes="Binary/export content is not stored in configuration snapshots.",
)
