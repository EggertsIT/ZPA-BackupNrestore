"""DELETE one CBI banner."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete",
    "DELETE",
    "/cbiconfig/cbi/api/customers/{customer_id}/banners/{id}",
    documentation_slug="isolation-banner-management/delete-zpa-banner-using-delete",
)
