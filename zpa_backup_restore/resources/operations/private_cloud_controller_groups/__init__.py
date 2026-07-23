"""Private Cloud Controller Group operation catalog."""

from .create_group import OPERATION as CREATE_GROUP
from .delete_group import OPERATION as DELETE_GROUP
from .get_group import OPERATION as GET_GROUP
from .list_groups import OPERATION as LIST_GROUPS
from .update_group import OPERATION as UPDATE_GROUP

OPERATIONS = (LIST_GROUPS, GET_GROUP, CREATE_GROUP, UPDATE_GROUP, DELETE_GROUP)

__all__ = ["CREATE_GROUP", "DELETE_GROUP", "GET_GROUP", "LIST_GROUPS", "OPERATIONS", "UPDATE_GROUP"]
