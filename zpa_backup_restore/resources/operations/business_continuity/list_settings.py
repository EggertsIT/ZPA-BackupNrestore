"""GET Business Continuity settings."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings",
    role="list",
    documentation_slug="business-continuity-settings/get-business-continuity-settings",
)
