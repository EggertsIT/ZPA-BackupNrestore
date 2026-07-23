"""Identity-reference API operations."""

from .get_idp import OPERATION as GET_IDP
from .get_saml_attribute import OPERATION as GET_SAML_ATTRIBUTE
from .get_scim_attribute import OPERATION as GET_SCIM_ATTRIBUTE
from .get_scim_group import OPERATION as GET_SCIM_GROUP
from .list_idps import OPERATION as LIST_IDPS
from .list_saml_attributes import OPERATION as LIST_SAML_ATTRIBUTES
from .list_saml_attributes_by_idp import OPERATION as LIST_SAML_ATTRIBUTES_BY_IDP
from .list_scim_attribute_values import OPERATION as LIST_SCIM_ATTRIBUTE_VALUES
from .list_scim_attributes import OPERATION as LIST_SCIM_ATTRIBUTES
from .list_scim_groups import OPERATION as LIST_SCIM_GROUPS

OPERATIONS = (
    LIST_IDPS,
    GET_IDP,
    LIST_SAML_ATTRIBUTES,
    LIST_SAML_ATTRIBUTES_BY_IDP,
    GET_SAML_ATTRIBUTE,
    LIST_SCIM_ATTRIBUTES,
    GET_SCIM_ATTRIBUTE,
    LIST_SCIM_ATTRIBUTE_VALUES,
    LIST_SCIM_GROUPS,
    GET_SCIM_GROUP,
)

__all__ = [
    "GET_IDP",
    "GET_SAML_ATTRIBUTE",
    "GET_SCIM_ATTRIBUTE",
    "GET_SCIM_GROUP",
    "LIST_IDPS",
    "LIST_SAML_ATTRIBUTES",
    "LIST_SAML_ATTRIBUTES_BY_IDP",
    "LIST_SCIM_ATTRIBUTE_VALUES",
    "LIST_SCIM_ATTRIBUTES",
    "LIST_SCIM_GROUPS",
    "OPERATIONS",
]
