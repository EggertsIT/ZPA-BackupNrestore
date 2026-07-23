"""Sensitive/high-impact configuration inventoried but not generically written."""

from .model import ResourceSpec
from .operations.business_continuity import OPERATIONS as BUSINESS_CONTINUITY_OPERATIONS
from .operations.private_cloud_controller_groups import OPERATIONS as CONTROLLER_GROUP_OPERATIONS
from .operations.private_clouds import OPERATIONS as PRIVATE_CLOUD_OPERATIONS

BUSINESS_CONTINUITY = ResourceSpec(
    key="business_continuity_settings",
    path=BUSINESS_CONTINUITY_OPERATIONS[0].path,
    detail_path=BUSINESS_CONTINUITY_OPERATIONS[1].path,
    writable=False,
    mode="audit",
    sensitivity="secret",
    high_impact=True,
    operations=BUSINESS_CONTINUITY_OPERATIONS,
    backup_skip_fields=frozenset(
        {
            "idpCert",
            "metaData",
            "sitespCACertificate",
            "sitespCAPrivateKey",
            "sitespCertificate",
            "sitespEncryptionCertificate",
            "sitespPrivateKey",
            "sitespSigningCertificate",
            "sitespSigningPrivateKey",
            "userIdpsMetaData",
        }
    ),
    notes="Sanitized inventory only; secret-bearing restore calls are cataloged but disabled.",
    optional=True,
)

PRIVATE_CLOUDS = ResourceSpec(
    key="private_clouds",
    path=PRIVATE_CLOUD_OPERATIONS[0].path,
    detail_path=PRIVATE_CLOUD_OPERATIONS[1].path,
    writable=False,
    mode="audit",
    sensitivity="high-impact",
    high_impact=True,
    operations=PRIVATE_CLOUD_OPERATIONS,
    notes="Inventory enabled; writes await deterministic two-phase association handling.",
    optional=True,
)

PRIVATE_CLOUD_CONTROLLER_GROUPS = ResourceSpec(
    key="private_cloud_controller_groups",
    path=CONTROLLER_GROUP_OPERATIONS[0].path,
    detail_path=CONTROLLER_GROUP_OPERATIONS[1].path,
    writable=False,
    mode="audit",
    sensitivity="high-impact",
    high_impact=True,
    operations=CONTROLLER_GROUP_OPERATIONS,
    notes="Inventory enabled; writes await deterministic site association handling.",
    optional=True,
)

SPECS = (BUSINESS_CONTINUITY, PRIVATE_CLOUDS, PRIVATE_CLOUD_CONTROLLER_GROUPS)
