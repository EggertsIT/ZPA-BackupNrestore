"""GET version profiles visible to a customer."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/visible/versionProfiles",
    pagination="page",
    documentation_slug="version-profile/get-all-version-profiles-visibile-by-customer-id",
)
