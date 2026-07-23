"""GET one Business Continuity setting."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/businessContinuitySettings/{id}",
    documentation_slug="business-continuity-settings/get-business-continuity-settings-by-id",
)
