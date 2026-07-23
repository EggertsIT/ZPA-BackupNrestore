"""GET SAML attributes scoped to an IdP."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list_by_idp",
    "GET",
    "/mgmtconfig/v2/admin/customers/{customer_id}/samlAttribute/idp/{idp_id}",
    pagination="page",
    documentation_slug="saml-attributes/get-all-attributes-by-idp-id-and-page",
)
