"""POST a PRA Portal."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "create", "POST", "/mgmtconfig/v1/admin/customers/{customer_id}/praPortal",
    documentation_slug="privileged-portal-management/add",
)
