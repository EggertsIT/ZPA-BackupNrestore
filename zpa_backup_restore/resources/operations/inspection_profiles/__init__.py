"""AppProtection inspection-profile operations."""

from .create_profile import OPERATION as CREATE
from .delete_profile import OPERATION as DELETE
from .get_profile import OPERATION as GET
from .list_profiles import OPERATION as LIST
from .update_profile import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
