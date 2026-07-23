"""GET one Posture Profile."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get", "GET", "/mgmtconfig/v1/admin/customers/{customer_id}/posture/{id}",
    documentation_slug="posture-profiles/gets-the-configured-posture-profile-for-the-specified-id",
)
