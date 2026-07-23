"""Cloud Browser Isolation banner API operations."""

from .create_banner import OPERATION as CREATE_BANNER
from .delete_banner import OPERATION as DELETE_BANNER
from .get_banner import OPERATION as GET_BANNER
from .list_banners import OPERATION as LIST_BANNERS
from .update_banner import OPERATION as UPDATE_BANNER

OPERATIONS = (LIST_BANNERS, GET_BANNER, CREATE_BANNER, UPDATE_BANNER, DELETE_BANNER)

__all__ = [
    "CREATE_BANNER",
    "DELETE_BANNER",
    "GET_BANNER",
    "LIST_BANNERS",
    "OPERATIONS",
    "UPDATE_BANNER",
]
