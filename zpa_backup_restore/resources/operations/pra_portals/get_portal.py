"""GET one PRA Portal."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/praPortal/{id}",
    documentation_slug="privileged-portal-management/get-pra-portal",
)
