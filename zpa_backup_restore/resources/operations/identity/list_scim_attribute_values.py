"""GET the values for one SCIM attribute."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list_scim_attribute_values", "GET",
    "/userconfig/v1/customers/{customer_id}/scimattribute/idpId/{idp_id}/attributeId/{id}",
    role="list_values", pagination="page",
    documentation_slug="scim-attributes/get-all-scim-attribute-values",
)
