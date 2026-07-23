"""Read-only policy-reference operations."""

from .get_machine_group import OPERATION as GET_MACHINE_GROUP
from .get_posture_profile import OPERATION as GET_POSTURE_PROFILE
from .get_trusted_network import OPERATION as GET_TRUSTED_NETWORK
from .list_machine_groups import OPERATION as LIST_MACHINE_GROUPS
from .list_posture_profiles import OPERATION as LIST_POSTURE_PROFILES
from .list_trusted_networks import OPERATION as LIST_TRUSTED_NETWORKS

__all__ = [
    "GET_MACHINE_GROUP",
    "GET_POSTURE_PROFILE",
    "GET_TRUSTED_NETWORK",
    "LIST_MACHINE_GROUPS",
    "LIST_POSTURE_PROFILES",
    "LIST_TRUSTED_NETWORKS",
]
