"""Audit-only operational objects that must never be generically cloned."""

from .model import ResourceSpec
from .operations.audit import (
    ACTIVATE_EMERGENCY_ACCESS_USER,
    CREATE_EMERGENCY_ACCESS_USER,
    CREATE_PRIVILEGED_APPROVAL,
    DEACTIVATE_EMERGENCY_ACCESS_USER,
    DELETE_EXPIRED_PRIVILEGED_APPROVALS,
    DELETE_PRIVATE_CLOUD_CONTROLLER,
    DELETE_PRIVILEGED_APPROVAL,
    GET_EMERGENCY_ACCESS_USER,
    GET_PRIVATE_CLOUD_CONTROLLER,
    GET_PRIVILEGED_APPROVAL,
    LIST_EMERGENCY_ACCESS_USERS,
    LIST_PRIVATE_CLOUD_CONTROLLERS,
    LIST_PRIVILEGED_APPROVALS,
    UPDATE_EMERGENCY_ACCESS_USER,
    UPDATE_PRIVATE_CLOUD_CONTROLLER,
    UPDATE_PRIVILEGED_APPROVAL,
)

PRIVATE_CLOUD_CONTROLLERS = ResourceSpec(
    key="private_cloud_controllers",
    path=LIST_PRIVATE_CLOUD_CONTROLLERS.path,
    detail_path=GET_PRIVATE_CLOUD_CONTROLLER.path,
    detail_strategy="list",
    writable=False,
    mode="audit",
    operations=(
        LIST_PRIVATE_CLOUD_CONTROLLERS,
        GET_PRIVATE_CLOUD_CONTROLLER,
        UPDATE_PRIVATE_CLOUD_CONTROLLER,
        DELETE_PRIVATE_CLOUD_CONTROLLER,
    ),
    notes="Live controller health and version inventory; deployment instances are never cloned.",
    optional=True,
)

EMERGENCY_ACCESS_USERS = ResourceSpec(
    key="emergency_access_users",
    path=LIST_EMERGENCY_ACCESS_USERS.path,
    detail_path=None,
    detail_strategy="list",
    id_field="userId",
    name_field="emailId",
    writable=False,
    mode="audit",
    sensitivity="sensitive",
    operations=(
        LIST_EMERGENCY_ACCESS_USERS,
        GET_EMERGENCY_ACCESS_USER,
        CREATE_EMERGENCY_ACCESS_USER,
        UPDATE_EMERGENCY_ACCESS_USER,
        ACTIVATE_EMERGENCY_ACCESS_USER,
        DEACTIVATE_EMERGENCY_ACCESS_USER,
    ),
    notes="Activation state is operational and is never generically restored.",
    optional=True,
)

PRIVILEGED_APPROVALS = ResourceSpec(
    key="privileged_approvals",
    path=LIST_PRIVILEGED_APPROVALS.path,
    detail_path=GET_PRIVILEGED_APPROVAL.path,
    detail_strategy="list",
    id_field="id",
    name_field="id",
    writable=False,
    mode="audit",
    sensitivity="sensitive",
    operations=(
        LIST_PRIVILEGED_APPROVALS,
        GET_PRIVILEGED_APPROVAL,
        CREATE_PRIVILEGED_APPROVAL,
        UPDATE_PRIVILEGED_APPROVAL,
        DELETE_PRIVILEGED_APPROVAL,
        DELETE_EXPIRED_PRIVILEGED_APPROVALS,
    ),
    notes="Time-windowed access approvals are inventory/audit data, not clone configuration.",
    optional=True,
)

SPECS = (
    PRIVATE_CLOUD_CONTROLLERS,
    EMERGENCY_ACCESS_USERS,
    PRIVILEGED_APPROVALS,
)
