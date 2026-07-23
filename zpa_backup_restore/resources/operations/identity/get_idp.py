"""GET one Identity Provider."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get_idp", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/idp/{id}",
    role="get",
    documentation_slug="idp-management/gets-details-of-the-id-p-for-the-specified-id",
)
