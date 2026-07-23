"""PUT one PRA Portal."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "update", "PUT", "/mgmtconfig/v1/admin/customers/{customer_id}/praPortal/{id}",
    documentation_slug="privileged-portal-management/update-pra-portal",
)
