"""Shared authentication and HTTP client adapter.

The adapter gives v2 services a stable package import while the independently
useful single-rule CLI remains backward compatible.
"""

from zpa_policy_tool import (
    AUTH_MODES,
    DEFAULT_AUDIENCE,
    DEFAULT_LEGACY_ZPA_BASE_URL,
    DEFAULT_ONEAPI_BASE_URL,
    ZscalerClient,
    add_query,
    dump_json,
    env,
    load_json,
    normalize_auth_mode,
    normalize_name,
    records_from,
    require_env,
)

__all__ = [
    "AUTH_MODES",
    "DEFAULT_AUDIENCE",
    "DEFAULT_LEGACY_ZPA_BASE_URL",
    "DEFAULT_ONEAPI_BASE_URL",
    "ZscalerClient",
    "add_query",
    "dump_json",
    "env",
    "load_json",
    "normalize_auth_mode",
    "normalize_name",
    "records_from",
    "require_env",
]
