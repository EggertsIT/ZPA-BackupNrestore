"""GET one SCIM group."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get_scim_group", "GET",
    "/userconfig/v1/customers/{customer_id}/scimgroup/{id}",
    role="get",
    documentation_slug="scim-groups/get-scim-group",
)
