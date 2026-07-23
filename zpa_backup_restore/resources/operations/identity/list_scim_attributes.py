"""GET SCIM attributes for one Identity Provider."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list_scim_attributes", "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/idp/{idp_id}/scimattribute",
    role="list", pagination="page",
    documentation_slug="scim-attributes/gets-all-scim-attributes-for-the-specified-id",
)
