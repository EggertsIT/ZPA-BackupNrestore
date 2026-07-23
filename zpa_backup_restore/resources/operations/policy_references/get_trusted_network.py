"""GET one Trusted Network."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/network/{id}",
    documentation_slug="trusted-networks/gets-the-trusted-networks-for-the-specified-id",
)
