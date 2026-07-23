"""GET all SAML attributes."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "list",
    "GET",
    "/mgmtconfig/v2/admin/customers/{customer_id}/samlAttribute",
    pagination="page",
    documentation_slug="saml-attributes/get-all-attributes-by-page",
)
