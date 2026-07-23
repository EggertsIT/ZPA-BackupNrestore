"""GET all AppProtection inspection profiles."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/inspectionProfile",
    pagination="page",
    documentation_slug="appprotection-profile-management/get-all-inspection-profiles",
)
