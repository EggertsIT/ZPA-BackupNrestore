"""POST an AppProtection inspection profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile",
    documentation_slug="appprotection-profile-management/add-inspection-profile",
)
