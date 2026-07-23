"""Privileged Remote Access Portal operations."""

from .create_portal import OPERATION as CREATE
from .delete_portal import OPERATION as DELETE
from .get_portal import OPERATION as GET
from .list_portals import OPERATION as LIST
from .update_portal import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
