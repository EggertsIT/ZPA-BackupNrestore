"""GET all Machine Groups."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup",
    pagination="page", documentation_slug="machine-groups/get-machine-groups",
)
