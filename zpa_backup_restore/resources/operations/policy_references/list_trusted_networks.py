"""GET all Trusted Networks."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v2/admin/customers/{customer_id}/network",
    pagination="page", documentation_slug="trusted-networks/get-all-trusted-networks",
)
