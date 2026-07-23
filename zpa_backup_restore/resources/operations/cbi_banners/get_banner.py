"""GET one CBI banner."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/cbiconfig/cbi/api/customers/{customer_id}/banners/{id}",
    documentation_slug="isolation-banner-management/get-cbi-banner-using-get",
)
