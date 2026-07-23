"""DELETE one CBI profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/cbiconfig/cbi/api/customers/{customer_id}/profiles/{id}",
    documentation_slug="isolation-profile-management/delete-zpa-profile-using-delete",
)
