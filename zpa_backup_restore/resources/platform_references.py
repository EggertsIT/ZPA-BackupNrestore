"""Read-only platform objects used to validate and remap restore payloads."""

from .model import ResourceSpec
from .operations.references import (
    GET_CLOUD_CONNECTOR_GROUP,
    GET_ENROLLMENT_CERTIFICATE,
    LIST_BROWSER_ACCESS_GROUPS,
    LIST_CLOUD_CONNECTOR_GROUPS,
    LIST_ENROLLMENT_CERTIFICATES,
    LIST_VERSION_PROFILES,
    LIST_ZSCALER_CLOUDS,
)

CLOUD_CONNECTOR_GROUPS = ResourceSpec(
    key="cloud_connector_groups",
    path=LIST_CLOUD_CONNECTOR_GROUPS.path,
    detail_path=GET_CLOUD_CONNECTOR_GROUP.path,
    writable=False,
    mode="reference",
    operations=(LIST_CLOUD_CONNECTOR_GROUPS, GET_CLOUD_CONNECTOR_GROUP),
    notes="Policy EDGE_CONNECTOR_GROUP reference inventory.",
    optional=True,
)

VERSION_PROFILES = ResourceSpec(
    key="version_profiles",
    path=LIST_VERSION_PROFILES.path,
    detail_path=None,
    detail_strategy="list",
    writable=False,
    mode="reference",
    operations=(LIST_VERSION_PROFILES,),
    notes="Version profiles referenced by connector and service component groups.",
)

ZSCALER_CLOUDS = ResourceSpec(
    key="zscaler_clouds",
    path=LIST_ZSCALER_CLOUDS.path,
    detail_path=None,
    detail_strategy="list",
    writable=False,
    mode="reference",
    operations=(LIST_ZSCALER_CLOUDS,),
    notes="Alternative Zscaler cloud catalog.",
)

ENROLLMENT_CERTIFICATES = ResourceSpec(
    key="enrollment_certificates",
    path=LIST_ENROLLMENT_CERTIFICATES.path,
    detail_path=None,
    detail_strategy="list",
    writable=False,
    mode="reference",
    sensitivity="sensitive",
    operations=(LIST_ENROLLMENT_CERTIFICATES, GET_ENROLLMENT_CERTIFICATE),
    backup_skip_fields=frozenset(
        {
            "certificate",
            "certificateBody",
            "certBlob",
            "csr",
            "privateKey",
            "pem",
        }
    ),
    notes="Metadata-only enrollment certificate inventory; no certificate bodies or private keys.",
    optional=True,
)

BROWSER_ACCESS_GROUPS = ResourceSpec(
    key="browser_access_groups",
    path=LIST_BROWSER_ACCESS_GROUPS.path,
    detail_path=None,
    detail_strategy="list",
    writable=False,
    mode="reference",
    operations=(LIST_BROWSER_ACCESS_GROUPS,),
    notes="Browser Access group inventory used by Browser Access application configuration.",
    optional=True,
)

SPECS = (
    CLOUD_CONNECTOR_GROUPS,
    VERSION_PROFILES,
    ZSCALER_CLOUDS,
    ENROLLMENT_CERTIFICATES,
    BROWSER_ACCESS_GROUPS,
)
