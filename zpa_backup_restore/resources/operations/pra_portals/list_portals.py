"""GET all PRA Portals."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/praPortal",
    pagination="page",
    documentation_slug="privileged-portal-management/gets-all-configured-privileged-portals-for-the-specified-customer",
)
