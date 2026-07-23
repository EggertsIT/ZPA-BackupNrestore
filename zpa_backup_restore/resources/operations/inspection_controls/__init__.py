"""AppProtection custom-control operations."""

from .create_control import OPERATION as CREATE
from .delete_control import OPERATION as DELETE
from .get_control import OPERATION as GET
from .list_controls import OPERATION as LIST
from .update_control import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
