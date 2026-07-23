"""Log Streaming Service configuration operations."""

from .create_config import OPERATION as CREATE
from .delete_config import OPERATION as DELETE
from .get_config import OPERATION as GET
from .list_configs import OPERATION as LIST
from .update_config import OPERATION as UPDATE

OPERATIONS = (LIST, GET, CREATE, UPDATE, DELETE)
__all__ = ["CREATE", "DELETE", "GET", "LIST", "OPERATIONS", "UPDATE"]
