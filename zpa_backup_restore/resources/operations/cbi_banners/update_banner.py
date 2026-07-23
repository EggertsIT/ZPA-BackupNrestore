"""PUT one CBI banner."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update",
    "PUT",
    "/cbiconfig/cbi/api/customers/{customer_id}/banners/{id}",
    documentation_slug="isolation-banner-management/update-zpa-banner-using-put",
)
