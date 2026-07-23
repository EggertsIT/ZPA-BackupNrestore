"""Application Segment special API operations."""

from .create_application import OPERATION as CREATE_APPLICATION
from .delete_application import OPERATION as DELETE_APPLICATION
from .get_application import OPERATION as GET_APPLICATION
from .list_applications import OPERATION as LIST_APPLICATIONS
from .move_application import OPERATION as MOVE_APPLICATION
from .share_application import OPERATION as SHARE_APPLICATION
from .update_application import OPERATION as UPDATE_APPLICATION

OPERATIONS = (
    LIST_APPLICATIONS,
    GET_APPLICATION,
    CREATE_APPLICATION,
    UPDATE_APPLICATION,
    DELETE_APPLICATION,
    MOVE_APPLICATION,
    SHARE_APPLICATION,
)

__all__ = [
    "CREATE_APPLICATION",
    "DELETE_APPLICATION",
    "GET_APPLICATION",
    "LIST_APPLICATIONS",
    "MOVE_APPLICATION",
    "OPERATIONS",
    "SHARE_APPLICATION",
    "UPDATE_APPLICATION",
]
