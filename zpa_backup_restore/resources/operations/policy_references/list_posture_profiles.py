"""GET all Posture Profiles."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list", "GET", "/mgmtconfig/v2/admin/customers/{customer_id}/posture",
    pagination="page", documentation_slug="posture-profiles/get-all-attributes",
)
