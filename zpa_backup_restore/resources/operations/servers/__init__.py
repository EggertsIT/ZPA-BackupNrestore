"""Application Server operations."""

from .create_server import OPERATION as CREATE
from .delete_server import OPERATION as DELETE
from .get_server import OPERATION as GET
from .list_servers import OPERATION as LIST
from .update_server import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
