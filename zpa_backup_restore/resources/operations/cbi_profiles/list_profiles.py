"""GET all CBI profiles."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/cbiconfig/cbi/api/customers/{customer_id}/profiles",
    pagination="page",
    documentation_slug="isolation-profile-management/get-all-profiles-from-cbi-using-get",
)
