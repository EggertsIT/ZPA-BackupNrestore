"""GET all Identity Providers."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list_idps", "GET", "/mgmtconfig/v2/admin/customers/{customer_id}/idp",
    role="list", pagination="page",
    documentation_slug="idp-management/get-all-idp",
)
