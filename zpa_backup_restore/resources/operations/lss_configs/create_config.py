"""POST an LSS configuration."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v2/admin/customers/{customer_id}/lssConfig",
    notes="Verified against the official Zscaler Python SDK; no dedicated sitemap page is currently exposed.",
)
