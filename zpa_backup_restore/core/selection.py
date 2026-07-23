"""Stable, auditable restore scopes for selective recovery."""

from __future__ import annotations

import copy
from collections import defaultdict, deque
from typing import Any, Iterable, Iterator

from zpa_backup_restore.core.catalog import MIGRATION_ORDER, POLICY_TYPES, RESOURCES
from zpa_backup_restore.core.diff import (
    compute_diff,
    identity_key,
    name_of,
    normalize_name,
)
from zpa_backup_restore.errors import CliError


RESTORE_SCOPE_SCHEMA_VERSION = "1.0"
SELECTABLE_RESOURCE_TYPES = tuple(MIGRATION_ORDER)


def resource_stable_key(resource_type: str, item: dict[str, Any]) -> str:
    """Return the same tenant-independent identity used by the diff engine."""
    if resource_type == "policy_rules":
        return identity_key(item, "name")
    meta = RESOURCES.get(resource_type)
    if not meta:
        raise CliError(f"Resource type is not selectable for restore: {resource_type}")
    return identity_key(item, meta.get("name_field", "name"))


def canonical_selector(resource_type: str, stable_key: str) -> str:
    return f"{resource_type}/{stable_key}"


def validate_restore_scope(scope: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(scope, dict):
        return ["scope must be an object"]
    if scope.get("schemaVersion") != RESTORE_SCOPE_SCHEMA_VERSION:
        issues.append(f"unsupported schemaVersion {scope.get('schemaVersion')!r}")
    if scope.get("mode") != "selected":
        issues.append(f"unsupported mode {scope.get('mode')!r}")
    if not isinstance(scope.get("requestedSelectors"), list):
        issues.append("requestedSelectors must be a list")
    selected_types = scope.get("selectedResourceTypes")
    if not isinstance(selected_types, list):
        issues.append("selectedResourceTypes must be a list")
        selected_types = []
    invalid_types = sorted(set(map(str, selected_types)) - set(SELECTABLE_RESOURCE_TYPES))
    if invalid_types:
        issues.append(
            "unsupported selected resource type(s): " + ", ".join(invalid_types)
        )
    resolved = scope.get("resolvedSelectors")
    if not isinstance(resolved, list):
        issues.append("resolvedSelectors must be a list")
        resolved = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(resolved):
        if not isinstance(item, dict):
            issues.append(f"resolvedSelectors[{index}] must be an object")
            continue
        resource_type = str(item.get("resourceType") or "")
        stable_key = str(item.get("stableKey") or "")
        if resource_type not in SELECTABLE_RESOURCE_TYPES:
            issues.append(
                f"resolvedSelectors[{index}] has unsupported resourceType {resource_type!r}"
            )
        if not stable_key:
            issues.append(f"resolvedSelectors[{index}] is missing stableKey")
        identity = (resource_type, stable_key)
        if identity in seen:
            issues.append(
                f"resolvedSelectors contains duplicate "
                f"{canonical_selector(resource_type, stable_key)}"
            )
        seen.add(identity)
        selector = item.get("selector")
        if selector and selector != canonical_selector(resource_type, stable_key):
            issues.append(f"resolvedSelectors[{index}] canonical selector does not match")
    if not selected_types and not resolved:
        issues.append("scope must select at least one object or resource type")
    if not isinstance(scope.get("referencedResources"), list):
        issues.append("referencedResources must be a list")
    if not isinstance(scope.get("includeDependencies"), bool):
        issues.append("includeDependencies must be true or false")
    if scope.get("policyOrder") not in {"preserve-target", "restore"}:
        issues.append("policyOrder must be 'preserve-target' or 'restore'")
    return issues


def _resource_items(backup: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for resource_type, value in backup.get("resources", {}).items():
        records = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        for item in records:
            if isinstance(item, dict):
                yield resource_type, item


def _display_name(resource_type: str, item: dict[str, Any]) -> str:
    name_field = "name" if resource_type == "policy_rules" else RESOURCES[resource_type].get(
        "name_field", "name"
    )
    return name_of(item, name_field)


def _source_index(
    source_backup: dict[str, Any],
) -> tuple[
    dict[str, dict[str, list[dict[str, Any]]]],
    dict[str, list[tuple[str, dict[str, Any]]]],
]:
    by_stable_key: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_id: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for resource_type, item in _resource_items(source_backup):
        if resource_type in SELECTABLE_RESOURCE_TYPES:
            by_stable_key[resource_type][resource_stable_key(resource_type, item)].append(item)
        source_id = item.get("id")
        if source_id is not None:
            by_id[str(source_id)].append((resource_type, item))
    return by_stable_key, by_id


def _parse_selector(value: str) -> tuple[str, str]:
    resource_type, separator, identity = value.strip().partition("/")
    if not separator or not resource_type or not identity:
        raise CliError(
            f"Invalid restore selector {value!r}; expected RESOURCE_TYPE/STABLE_KEY"
        )
    if resource_type not in SELECTABLE_RESOURCE_TYPES:
        raise CliError(
            f"Resource type is not selectable for restore: {resource_type}. "
            f"Choose one of: {', '.join(SELECTABLE_RESOURCE_TYPES)}"
        )
    if identity == "*":
        return resource_type, "*"
    if resource_type == "policy_rules":
        if "/" in identity:
            policy_type, rule_name = identity.split("/", 1)
            if policy_type not in POLICY_TYPES:
                raise CliError(f"Unsupported policy type in restore selector: {policy_type}")
            stable_key = f"{policy_type}:{normalize_name(rule_name)}"
        else:
            policy_type, separator, rule_key = identity.partition(":")
            if not separator or not rule_key:
                raise CliError(
                    "Policy-rule selectors require "
                    "policy_rules/POLICY_TYPE:stable-name or "
                    "policy_rules/POLICY_TYPE/Rule Name"
                )
            if policy_type not in POLICY_TYPES:
                raise CliError(f"Unsupported policy type in restore selector: {policy_type}")
            stable_key = f"{policy_type}:{normalize_name(rule_key)}"
        return resource_type, stable_key
    return resource_type, normalize_name(identity)


def _walk_reference_values(value: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_reference_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_reference_values(child, f"{path}[{index}]")
    else:
        yield path, value


def build_restore_scope(
    source_backup: dict[str, Any],
    *,
    selectors: Iterable[str] = (),
    resource_types: Iterable[str] = (),
    include_dependencies: bool = False,
    restore_policy_order: bool = False,
) -> dict[str, Any] | None:
    """Resolve requested selectors against the desired backup.

    Returns ``None`` for the legacy full-backup scope.
    """
    requested_selectors = [str(value).strip() for value in selectors if str(value).strip()]
    requested_resource_types = [
        str(value).strip() for value in resource_types if str(value).strip()
    ]
    if not requested_selectors and not requested_resource_types:
        if include_dependencies or restore_policy_order:
            raise CliError(
                "--include-dependencies and --restore-policy-order require "
                "--select or --select-resource"
            )
        return None

    whole_types: set[str] = set()
    parsed: list[tuple[str, str]] = []
    for resource_type in requested_resource_types:
        if resource_type not in SELECTABLE_RESOURCE_TYPES:
            raise CliError(
                f"Resource type is not selectable for restore: {resource_type}. "
                f"Choose one of: {', '.join(SELECTABLE_RESOURCE_TYPES)}"
            )
        whole_types.add(resource_type)
    for selector in requested_selectors:
        resource_type, stable_key = _parse_selector(selector)
        if stable_key == "*":
            whole_types.add(resource_type)
        else:
            parsed.append((resource_type, stable_key))

    by_stable_key, by_id = _source_index(source_backup)
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    reasons: dict[tuple[str, str], str] = {}

    for resource_type in sorted(whole_types):
        for stable_key, matches in by_stable_key.get(resource_type, {}).items():
            if len(matches) > 1:
                raise CliError(
                    f"Restore selection is ambiguous: "
                    f"{canonical_selector(resource_type, stable_key)} matches "
                    f"{len(matches)} desired objects"
                )
            selected[(resource_type, stable_key)] = matches[0]
            reasons[(resource_type, stable_key)] = "resource-type"

    for resource_type, stable_key in parsed:
        matches = by_stable_key.get(resource_type, {}).get(stable_key, [])
        selector = canonical_selector(resource_type, stable_key)
        if not matches:
            raise CliError(f"Restore selector was not found in the desired backup: {selector}")
        if len(matches) > 1:
            raise CliError(
                f"Restore selector is ambiguous: {selector} matches {len(matches)} desired objects"
            )
        selected[(resource_type, stable_key)] = matches[0]
        reasons[(resource_type, stable_key)] = "selected"

    referenced: dict[tuple[str, str], dict[str, str]] = {}
    queue = deque(sorted(selected))
    visited: set[tuple[str, str]] = set()
    while queue:
        current_key = queue.popleft()
        if current_key in visited:
            continue
        visited.add(current_key)
        item = selected[current_key]
        for path, value in _walk_reference_values(item):
            if path == "$.id" or value is None:
                continue
            matches = by_id.get(str(value), [])
            if len(matches) != 1:
                continue
            dependency_type, dependency = matches[0]
            if dependency_type in SELECTABLE_RESOURCE_TYPES:
                dependency_key = resource_stable_key(dependency_type, dependency)
            else:
                dependency_key = normalize_name(
                    dependency.get("name")
                    or dependency.get("displayName")
                    or dependency.get("id")
                    or ""
                )
            reference_key = (dependency_type, dependency_key)
            referenced[reference_key] = {
                "resourceType": dependency_type,
                "stableKey": dependency_key,
                "displayName": str(
                    dependency.get("name")
                    or dependency.get("displayName")
                    or dependency.get("id")
                    or ""
                ),
                "fieldPath": path,
            }
            if (
                include_dependencies
                and dependency_type in SELECTABLE_RESOURCE_TYPES
                and reference_key not in selected
            ):
                selected[reference_key] = dependency
                reasons[reference_key] = "dependency"
                queue.append(reference_key)

    resolved = [
        {
            "resourceType": resource_type,
            "stableKey": stable_key,
            "displayName": _display_name(resource_type, selected[(resource_type, stable_key)]),
            "reason": reasons[(resource_type, stable_key)],
            "selector": canonical_selector(resource_type, stable_key),
        }
        for resource_type, stable_key in sorted(selected)
    ]
    return {
        "schemaVersion": RESTORE_SCOPE_SCHEMA_VERSION,
        "mode": "selected",
        "requestedSelectors": requested_selectors,
        "selectedResourceTypes": sorted(whole_types),
        "resolvedSelectors": resolved,
        "referencedResources": [
            referenced[key] for key in sorted(referenced)
        ],
        "includeDependencies": include_dependencies,
        "policyOrder": "restore" if restore_policy_order else "preserve-target",
    }


def _selected_keys(scope: dict[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
    whole_types = {
        str(resource_type) for resource_type in scope.get("selectedResourceTypes", [])
    }
    keys: dict[str, set[str]] = defaultdict(set)
    for selector in scope.get("resolvedSelectors", []) or []:
        if not isinstance(selector, dict):
            continue
        resource_type = str(selector.get("resourceType") or "")
        stable_key = str(selector.get("stableKey") or "")
        if resource_type and stable_key:
            keys[resource_type].add(stable_key)
    return whole_types, keys


def _matches(
    resource_type: str,
    item: dict[str, Any],
    whole_types: set[str],
    keys: dict[str, set[str]],
) -> bool:
    return resource_type in whole_types or resource_stable_key(resource_type, item) in keys.get(
        resource_type, set()
    )


def _filter_section(
    section: dict[str, Any],
    *,
    resource_type: str,
    whole_types: set[str],
    keys: dict[str, set[str]],
) -> dict[str, Any]:
    result = {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}
    for bucket in ("to_create", "to_delete", "unchanged"):
        result[bucket] = [
            copy.deepcopy(item)
            for item in section.get(bucket, []) or []
            if isinstance(item, dict)
            and _matches(resource_type, item, whole_types, keys)
        ]
    result["to_update"] = [
        copy.deepcopy(change)
        for change in section.get("to_update", []) or []
        if isinstance(change, dict)
        and isinstance(change.get("source") or change.get("target"), dict)
        and _matches(
            resource_type,
            change.get("source") or change.get("target"),
            whole_types,
            keys,
        )
    ]
    return result


def _summary(section: dict[str, Any]) -> dict[str, int]:
    return {
        "create": len(section.get("to_create", []) or []),
        "update": len(section.get("to_update", []) or []),
        "delete": len(section.get("to_delete", []) or []),
        "unchanged": len(section.get("unchanged", []) or []),
    }


def apply_restore_scope(
    full_diff: dict[str, Any],
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    if scope is None:
        return full_diff
    issues = validate_restore_scope(scope)
    if issues:
        raise CliError(
            "Restore scope is invalid:\n" + "\n".join(f"- {issue}" for issue in issues)
        )

    whole_types, keys = _selected_keys(scope)
    scoped = {
        "meta": copy.deepcopy(full_diff.get("meta", {})),
        "scope": copy.deepcopy(scope),
        "resources": {},
        "summary": {},
    }
    for resource_type in MIGRATION_ORDER:
        section = _filter_section(
            full_diff.get("resources", {}).get(resource_type, {}),
            resource_type=resource_type,
            whole_types=whole_types,
            keys=keys,
        )
        scoped["resources"][resource_type] = section
        scoped["summary"][resource_type] = _summary(section)

    for special_type in ("application_segment_moves", "application_segment_shares"):
        section = _filter_section(
            full_diff.get("resources", {}).get(special_type, {}),
            resource_type="application_segments",
            whole_types=whole_types,
            keys=keys,
        )
        scoped["resources"][special_type] = section
        scoped["summary"][special_type] = _summary(section)

    policy_order = {"to_create": [], "to_update": [], "to_delete": [], "unchanged": []}
    if scope.get("policyOrder") == "restore":
        allowed_policy_types = {
            stable_key.split(":", 1)[0]
            for stable_key in keys.get("policy_rules", set())
            if ":" in stable_key
        }
        all_policy_rules = "policy_rules" in whole_types
        source_section = full_diff.get("resources", {}).get("policy_rule_order", {})
        for bucket in ("to_update", "unchanged"):
            for item in source_section.get(bucket, []) or []:
                record = item.get("source", {}) if bucket == "to_update" else item
                policy_type = str(
                    record.get("_policyTypeName") or record.get("name") or ""
                )
                if all_policy_rules or policy_type in allowed_policy_types:
                    policy_order[bucket].append(copy.deepcopy(item))
    scoped["resources"]["policy_rule_order"] = policy_order
    scoped["summary"]["policy_rule_order"] = _summary(policy_order)
    return scoped


def compute_restore_diff(
    source_backup: dict[str, Any],
    target_backup: dict[str, Any],
    *,
    scope: dict[str, Any] | None = None,
    selectors: Iterable[str] = (),
    resource_types: Iterable[str] = (),
    include_dependencies: bool = False,
    restore_policy_order: bool = False,
) -> dict[str, Any]:
    selector_values = tuple(selectors)
    resource_type_values = tuple(resource_types)
    if scope is not None and (
        selector_values
        or resource_type_values
        or include_dependencies
        or restore_policy_order
    ):
        raise CliError("Pass either a persisted restore scope or new selectors, not both")
    resolved_scope = scope
    if resolved_scope is None:
        resolved_scope = build_restore_scope(
            source_backup,
            selectors=selector_values,
            resource_types=resource_type_values,
            include_dependencies=include_dependencies,
            restore_policy_order=restore_policy_order,
        )
    return apply_restore_scope(compute_diff(source_backup, target_backup), resolved_scope)


def scope_from_diff(diff: dict[str, Any]) -> dict[str, Any] | None:
    scope = diff.get("scope")
    if scope is None:
        return None
    issues = validate_restore_scope(scope)
    if issues:
        raise CliError(
            "Restore diff scope is invalid:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )
    return scope


def scope_inventory_keys(scope: dict[str, Any] | None) -> tuple[set[str], dict[str, set[str]]]:
    """Public filtering helper for scoped assurance hashes."""
    if scope is None:
        return set(), {}
    return _selected_keys(scope)


__all__ = [
    "RESTORE_SCOPE_SCHEMA_VERSION",
    "SELECTABLE_RESOURCE_TYPES",
    "apply_restore_scope",
    "build_restore_scope",
    "canonical_selector",
    "compute_restore_diff",
    "resource_stable_key",
    "scope_from_diff",
    "scope_inventory_keys",
    "validate_restore_scope",
]
