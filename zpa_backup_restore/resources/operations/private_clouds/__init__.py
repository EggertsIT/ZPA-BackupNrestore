"""Private Cloud/Site operation catalog."""

from .create_site import OPERATION as CREATE_SITE
from .delete_site import OPERATION as DELETE_SITE
from .get_site import OPERATION as GET_SITE
from .list_sites import OPERATION as LIST_SITES
from .update_site import OPERATION as UPDATE_SITE

OPERATIONS = (LIST_SITES, GET_SITE, CREATE_SITE, UPDATE_SITE, DELETE_SITE)

__all__ = ["CREATE_SITE", "DELETE_SITE", "GET_SITE", "LIST_SITES", "OPERATIONS", "UPDATE_SITE"]
