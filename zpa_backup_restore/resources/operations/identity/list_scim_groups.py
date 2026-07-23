"""GET SCIM groups for one Identity Provider."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list_scim_groups", "GET",
    "/userconfig/v1/customers/{customer_id}/scimgroup/idpId/{idp_id}",
    role="list", pagination="page",
    documentation_slug="scim-groups/get-all-scim-groups",
)
