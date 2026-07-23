"""IdP, SAML, and SCIM read-only reference API paths."""

from .operations.identity import LIST_SAML_ATTRIBUTES_BY_IDP

READ_ONLY_REFERENCE_RESOURCES = (
    "idps",
    "saml_attributes",
    "scim_attributes",
    "scim_groups",
)


def idps_path(customer_id: str) -> str:
    return f"/mgmtconfig/v2/admin/customers/{customer_id}/idp"


def scim_attributes_path(customer_id: str, idp_id: str) -> str:
    return f"/mgmtconfig/v1/admin/customers/{customer_id}/idp/{idp_id}/scimattribute"


def saml_attributes_path(customer_id: str, idp_id: str) -> str:
    return LIST_SAML_ATTRIBUTES_BY_IDP.path.format(customer_id=customer_id, idp_id=idp_id)


def scim_groups_path(customer_id: str, idp_id: str) -> str:
    return f"/userconfig/v1/customers/{customer_id}/scimgroup/idpId/{idp_id}"
