"""Policy Rule API paths, supported types, and deterministic order helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

POLICY_TYPES = (
    "ACCESS_POLICY",
    "TIMEOUT_POLICY",
    "CLIENT_FORWARDING_POLICY",
    "INSPECTION_POLICY",
    "ISOLATION_POLICY",
    "CREDENTIAL_POLICY",
    "CAPABILITIES_POLICY",
    "CLIENTLESS_SESSION_PROTECTION_POLICY",
    "REDIRECTION_POLICY",
    "PRIVILEGED_PORTAL_POLICY",
)


def policy_set_path(customer_id: str, policy_type: str) -> str:
    return f"/mgmtconfig/v1/admin/customers/{customer_id}/policySet/policyType/{policy_type}"


def policy_rules_path(customer_id: str, policy_type: str) -> str:
    return f"/mgmtconfig/v1/admin/customers/{customer_id}/policySet/rules/policyType/{policy_type}"


def policy_rule_path(customer_id: str, policy_set_id: str, rule_id: str | None = None, *, version: str = "v2") -> str:
    path = f"/mgmtconfig/{version}/admin/customers/{customer_id}/policySet/{policy_set_id}/rule"
    return f"{path}/{rule_id}" if rule_id is not None else path


def policy_reorder_path(customer_id: str, policy_set_id: str) -> str:
    return f"/mgmtconfig/v1/admin/customers/{customer_id}/policySet/{policy_set_id}/reorder"


def _normalized_name(rule: dict[str, Any]) -> str:
    return "".join(str(rule.get("name") or rule.get("id") or "").casefold().split())


def _order_value(rule: dict[str, Any], fallback: int) -> tuple[int, int]:
    try:
        return int(rule.get("ruleOrder")), fallback
    except (TypeError, ValueError):
        return fallback, fallback


def rules_by_policy_type(rules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, rule in enumerate(rules):
        policy_type = str(rule.get("_policyTypeName") or rule.get("policyType") or "")
        if policy_type:
            grouped[policy_type].append((index, rule))
    return {
        policy_type: [
            rule
            for index, rule in sorted(
                values,
                key=lambda pair: _order_value(pair[1], pair[0]),
            )
        ]
        for policy_type, values in grouped.items()
    }


def policy_order_section(
    source_rules: list[dict[str, Any]],
    target_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return synthetic diff changes for policy sets whose rule order differs."""
    source_by_type = rules_by_policy_type(source_rules)
    target_by_type = rules_by_policy_type(target_rules)
    changes = []
    unchanged = []
    for policy_type in sorted(set(source_by_type) | set(target_by_type)):
        source = source_by_type.get(policy_type, [])
        target = target_by_type.get(policy_type, [])
        source_names = [_normalized_name(rule) for rule in source]
        target_names = [_normalized_name(rule) for rule in target]
        record = {
            "source": {
                "name": policy_type,
                "_policyTypeName": policy_type,
                "rules": source,
            },
            "target": {
                "name": policy_type,
                "_policyTypeName": policy_type,
                "rules": target,
            },
        }
        if source_names == target_names:
            unchanged.append(record["source"])
        else:
            changes.append(record)
    return {
        "to_create": [],
        "to_update": changes,
        "to_delete": [],
        "unchanged": unchanged,
    }


def policy_reorder_ids(
    change: dict[str, Any],
    lookup: Callable[[Any], Any],
    *,
    retain_target_extras: bool,
) -> list[str]:
    """Resolve the complete destination rule-ID order for one policy set."""
    source_rules = change.get("source", {}).get("rules", []) or []
    target_rules = change.get("target", {}).get("rules", []) or []
    ordered = [str(lookup(rule.get("id"))) for rule in source_rules if rule.get("id") is not None]
    if retain_target_extras:
        used = set(ordered)
        ordered.extend(
            str(rule["id"])
            for rule in target_rules
            if rule.get("id") is not None and str(rule["id"]) not in used
        )
    return ordered


__all__ = [
    "POLICY_TYPES",
    "policy_order_section",
    "policy_reorder_ids",
    "policy_reorder_path",
    "policy_rule_path",
    "policy_rules_path",
    "policy_set_path",
    "rules_by_policy_type",
]
