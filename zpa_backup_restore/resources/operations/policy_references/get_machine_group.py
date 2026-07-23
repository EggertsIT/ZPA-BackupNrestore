"""GET one Machine Group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup/{id}",
    documentation_slug="machine-groups/get-machine-group",
)
