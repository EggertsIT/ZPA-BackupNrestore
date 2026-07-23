"""GET all custom AppProtection controls."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionControls/custom",
    pagination="page",
    documentation_slug="appprotection-control-management/get-all-custom-controls",
)
