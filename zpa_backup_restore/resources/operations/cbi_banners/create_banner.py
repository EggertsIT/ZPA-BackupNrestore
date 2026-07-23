"""POST one CBI banner."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create",
    "POST",
    "/cbiconfig/cbi/api/customers/{customer_id}/banner",
    documentation_slug="isolation-banner-management/add-cbi-banner-using-post",
)
