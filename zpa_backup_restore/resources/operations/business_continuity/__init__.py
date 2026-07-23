"""Business Continuity operation catalog."""

from .create_settings import OPERATION as CREATE_SETTINGS
from .delete_settings import OPERATION as DELETE_SETTINGS
from .download_metadata import OPERATION as DOWNLOAD_METADATA
from .download_sp_certificate import OPERATION as DOWNLOAD_SP_CERTIFICATE
from .get_settings import OPERATION as GET_SETTINGS
from .list_settings import OPERATION as LIST_SETTINGS
from .update_settings import OPERATION as UPDATE_SETTINGS

OPERATIONS = (
    LIST_SETTINGS,
    GET_SETTINGS,
    CREATE_SETTINGS,
    UPDATE_SETTINGS,
    DELETE_SETTINGS,
    DOWNLOAD_METADATA,
    DOWNLOAD_SP_CERTIFICATE,
)

__all__ = [
    "CREATE_SETTINGS",
    "DELETE_SETTINGS",
    "DOWNLOAD_METADATA",
    "DOWNLOAD_SP_CERTIFICATE",
    "GET_SETTINGS",
    "LIST_SETTINGS",
    "OPERATIONS",
    "UPDATE_SETTINGS",
]
