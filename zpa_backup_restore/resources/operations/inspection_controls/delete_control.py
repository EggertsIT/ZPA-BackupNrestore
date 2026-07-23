"""DELETE one custom AppProtection control."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "delete", "DELETE", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom/{id}",
    documentation_slug="appprotection-control-management/delete-custom-control",
)
