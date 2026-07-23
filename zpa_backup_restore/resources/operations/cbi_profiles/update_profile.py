"""PUT one CBI profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/cbiconfig/cbi/api/customers/{customer_id}/profiles/{id}",
    documentation_slug="isolation-profile-management/update-zpa-profile-using-put",
)
