"""Cloud Browser Isolation API definitions."""

from .model import ResourceSpec
from .operations.cbi_banners import OPERATIONS as BANNER_OPERATIONS
from .operations.cbi_profiles import OPERATIONS as PROFILE_OPERATIONS

BANNERS = ResourceSpec(
    key="cbi_banners",
    path="/cbiconfig/cbi/api/customers/{customer_id}/banners",
    detail_path="/cbiconfig/cbi/api/customers/{customer_id}/banners/{id}",
    operations=BANNER_OPERATIONS,
    notes="Cloud Browser Isolation banner configuration.",
    optional=True,
)

PROFILES = ResourceSpec(
    key="cbi_profiles",
    path="/cbiconfig/cbi/api/customers/{customer_id}/profiles",
    detail_path="/cbiconfig/cbi/api/customers/{customer_id}/profiles/{id}",
    operations=PROFILE_OPERATIONS,
    notes="Cloud Browser Isolation profiles.",
)

SPECS = (BANNERS, PROFILES)
