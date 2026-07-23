"""Catalog the Business Continuity SP certificate download."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "download_sp_certificate",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings/certificate",
    role="export",
    support="excluded",
    documentation_slug="business-continuity-settings/download-sp-certificate",
    notes="Certificate material is excluded from generic snapshots.",
)
