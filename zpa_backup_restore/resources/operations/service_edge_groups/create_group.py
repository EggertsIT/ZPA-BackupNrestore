"""POST a Private Service Edge group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/serviceEdgeGroup",
    notes="Verified against the official Zscaler Python SDK; no dedicated sitemap page is currently exposed.",
)
