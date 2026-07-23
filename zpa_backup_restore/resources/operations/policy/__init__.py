"""Policy-management API operations."""

from .create_policy_rule import OPERATION as CREATE_POLICY_RULE
from .delete_policy_rule import OPERATION as DELETE_POLICY_RULE
from .get_policy_rule import OPERATION as GET_POLICY_RULE
from .get_policy_set import OPERATION as GET_POLICY_SET
from .list_policy_rules import OPERATION as LIST_POLICY_RULES
from .bulk_reorder_rules import OPERATION as BULK_REORDER_RULES
from .reorder_rule import OPERATION as REORDER_RULE
from .update_policy_rule import OPERATION as UPDATE_POLICY_RULE

OPERATIONS = (
    GET_POLICY_SET,
    LIST_POLICY_RULES,
    GET_POLICY_RULE,
    CREATE_POLICY_RULE,
    UPDATE_POLICY_RULE,
    DELETE_POLICY_RULE,
    REORDER_RULE,
    BULK_REORDER_RULES,
)

__all__ = [
    "BULK_REORDER_RULES",
    "CREATE_POLICY_RULE",
    "DELETE_POLICY_RULE",
    "GET_POLICY_RULE",
    "GET_POLICY_SET",
    "LIST_POLICY_RULES",
    "OPERATIONS",
    "REORDER_RULE",
    "UPDATE_POLICY_RULE",
]
