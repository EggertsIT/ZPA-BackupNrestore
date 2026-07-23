"""Read-only policy-reference inventory API definitions."""

from .model import ResourceSpec
from .operations.policy_references import (
    GET_MACHINE_GROUP,
    GET_POSTURE_PROFILE,
    GET_TRUSTED_NETWORK,
    LIST_MACHINE_GROUPS,
    LIST_POSTURE_PROFILES,
    LIST_TRUSTED_NETWORKS,
)

MACHINE_GROUPS = ResourceSpec(
    key="machine_groups",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/machineGroup/{id}",
    operations=(LIST_MACHINE_GROUPS, GET_MACHINE_GROUP),
    writable=False,
    mode="reference",
    notes="Machine group inventory; no generic writes are modeled.",
)

POSTURE_PROFILES = ResourceSpec(
    key="posture_profiles",
    path="/mgmtconfig/v2/admin/customers/{customer_id}/posture",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/posture/{id}",
    operations=(LIST_POSTURE_PROFILES, GET_POSTURE_PROFILE),
    writable=False,
    mode="reference",
    notes="Target posture profiles must already exist for policy ID remapping.",
)

TRUSTED_NETWORKS = ResourceSpec(
    key="trusted_networks",
    path="/mgmtconfig/v2/admin/customers/{customer_id}/network",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/network/{id}",
    operations=(LIST_TRUSTED_NETWORKS, GET_TRUSTED_NETWORK),
    writable=False,
    mode="reference",
    notes="Target trusted networks must already exist for policy ID remapping.",
)

SPECS = (MACHINE_GROUPS, POSTURE_PROFILES, TRUSTED_NETWORKS)
