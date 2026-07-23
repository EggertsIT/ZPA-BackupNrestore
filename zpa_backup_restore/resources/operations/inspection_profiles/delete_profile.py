"""DELETE one AppProtection inspection profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile/{id}",
    documentation_slug="appprotection-profile-management/delete-inspection-profile",
)
