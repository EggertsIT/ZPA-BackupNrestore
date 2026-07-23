"""PUT one custom AppProtection control."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom/{id}",
    documentation_slug="appprotection-control-management/update-custom-control",
)
