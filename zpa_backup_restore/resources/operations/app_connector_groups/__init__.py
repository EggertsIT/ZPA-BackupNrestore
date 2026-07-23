"""App Connector Group operations."""

from .create_group import OPERATION as CREATE
from .delete_group import OPERATION as DELETE
from .get_group import OPERATION as GET
from .list_groups import OPERATION as LIST
from .update_group import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
