"""POST a CBI profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/cbiconfig/cbi/api/customers/{customer_id}/profiles",
    documentation_slug="isolation-profile-management/add-zpa-profile-using-post",
)
