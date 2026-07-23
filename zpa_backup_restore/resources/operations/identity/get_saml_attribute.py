"""GET one SAML attribute."""

from zpa_backup_restore.resources.model import operation

OPERATION = operation(
    "get",
    "GET",
    "/mgmtconfig/v1/admin/customers/{customer_id}/samlAttribute/{id}",
    documentation_slug="saml-attributes/gets-the-saml-attribute-details-for-the-specified-id",
)
