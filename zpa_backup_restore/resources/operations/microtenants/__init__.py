"""Microtenant API operations."""

from .create_microtenant import OPERATION as CREATE
from .delete_microtenant import OPERATION as DELETE
from .get_microtenant import OPERATION as GET
from .list_microtenants import OPERATION as LIST
from .update_microtenant import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
