"""POST a custom AppProtection control."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom",
    documentation_slug="appprotection-control-management/create-custom-control",
)
