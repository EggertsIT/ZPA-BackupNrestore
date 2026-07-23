"""GET all CBI banners."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/cbiconfig/cbi/api/customers/{customer_id}/banners",
    pagination="page",
    documentation_slug="isolation-banner-management/get-all-cbi-banner-using-get",
)
