"""Privileged Remote Access Console operations."""

from .create_console import OPERATION as CREATE
from .delete_console import OPERATION as DELETE
from .get_console import OPERATION as GET
from .list_consoles import OPERATION as LIST
from .update_console import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
