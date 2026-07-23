"""GET one SCIM attribute."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get_scim_attribute", "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/idp/{idp_id}/scimattribute/{id}",
    role="get",
    documentation_slug="scim-attributes/gets-the-scim-attribute-details-for-the-specified-id",
)
