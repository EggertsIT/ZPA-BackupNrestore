"""Shared redaction policy for persisted reports and simulations."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_MARKERS = (
    "secret",
    "password",
    "token",
    "privatekey",
    "private_key",
    "apikey",
    "api_key",
    "clientsecret",
    "client_secret",
    "preshared",
    "pre_shared",
    "certificate",
    "certchain",
)
SENSITIVE_TEXT_RE = re.compile(
    r'("?(?:access[_-]?token|authorization|client[_-]?id|client[_-]?secret|password|refresh[_-]?token|secret|token)"?\s*[:=]\s*)("[^"]*"|[^,\s}]+)',
    re.IGNORECASE,
)


def is_sensitive_key(key: str) -> bool:
    compact = key.replace("-", "").replace("_", "").casefold()
    return any(marker.replace("_", "") in compact for marker in SENSITIVE_MARKERS)


def redact(value: Any, key_name: str = "") -> Any:
    """Return a JSON-compatible copy with sensitive-looking fields masked."""
    if key_name and is_sensitive_key(key_name):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {key: redact(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child, key_name) for child in value]
    if isinstance(value, tuple):
        return [redact(child, key_name) for child in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    return SENSITIVE_TEXT_RE.sub(r"\1[REDACTED]", value)


__all__ = ["SENSITIVE_MARKERS", "is_sensitive_key", "redact", "redact_text"]
