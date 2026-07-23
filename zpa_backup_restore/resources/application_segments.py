"""Application Segment API definition and list-detail exception."""

from typing import Any

from .model import ResourceSpec
from .operations.application_segments import MOVE_APPLICATION, OPERATIONS, SHARE_APPLICATION

PLACEMENT_FIELDS = frozenset(
    {
        "microtenantId",
        "microtenantName",
        "sharedMicrotenantDetails",
    }
)

SPEC = ResourceSpec(
    key="application_segments",
    path="/mgmtconfig/v1/admin/customers/{customer_id}/application",
    detail_path="/mgmtconfig/v1/admin/customers/{customer_id}/application/{id}",
    detail_strategy="list",
    operations=OPERATIONS,
    skip_fields=PLACEMENT_FIELDS,
    depends_on=(
        "segment_groups",
        "server_groups",
        "service_edge_groups",
        "inspection_profiles",
        "cbi_profiles",
    ),
    notes="The paginated list returns detailed records, avoiding one detail request per segment.",
)


def _stable(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def _shared_to(item: dict[str, Any]) -> list[dict[str, Any]]:
    details = item.get("sharedMicrotenantDetails") or {}
    if not isinstance(details, dict):
        return []
    shared = details.get("sharedToMicrotenants") or []
    if isinstance(shared, dict):
        shared = [shared]
    return [entry for entry in shared if isinstance(entry, dict)]


def _server_group_ids(item: dict[str, Any]) -> list[Any]:
    groups = item.get("serverGroups") or []
    return [
        group.get("id")
        for group in groups
        if isinstance(group, dict) and group.get("id") is not None
    ]


def special_operation_sections(
    source_items: list[dict[str, Any]],
    target_items: list[dict[str, Any]],
) -> dict[str, dict[str, list[Any]]]:
    """Diff move/share state separately from the ordinary update payload."""
    target_by_name = {
        _stable(item.get("name")): item
        for item in target_items
        if isinstance(item, dict)
    }
    moves: list[dict[str, Any]] = []
    shares: list[dict[str, Any]] = []
    for source in source_items:
        if not isinstance(source, dict):
            continue
        target = target_by_name.get(_stable(source.get("name")))
        planned_target = {
            "id": source.get("id"),
            "name": source.get("name"),
            "_planned": True,
        }

        source_tenant = _stable(source.get("microtenantName"))
        target_tenant = _stable(target.get("microtenantName")) if target else "default"
        source_is_non_default = (
            source_tenant not in {"", "default", "defaultmicrotenant"}
            if source_tenant
            else str(source.get("microtenantId")) not in {"", "0", "None"}
        )
        if source_is_non_default and source_tenant != target_tenant:
            server_group_ids = _server_group_ids(source)
            issue = ""
            if target and target_tenant not in {"default", "defaultmicrotenant"}:
                issue = "ZPA only supports moving an application from the default Microtenant"
            elif source.get("microtenantId") is None or source.get("segmentGroupId") is None:
                issue = "move destination Microtenant or Segment Group is missing"
            elif len(server_group_ids) != 1:
                issue = "move requires exactly one destination Server Group"
            moves.append(
                {
                    "source": {
                        "id": source.get("id"),
                        "name": source.get("name"),
                        "targetMicrotenantId": source.get("microtenantId"),
                        "targetSegmentGroupId": source.get("segmentGroupId"),
                        "targetServerGroupId": (
                            server_group_ids[0] if len(server_group_ids) == 1 else None
                        ),
                        "_issue": issue,
                    },
                    "target": {
                        "id": target.get("id"),
                        "name": target.get("name"),
                        "microtenantId": target.get("microtenantId"),
                        "microtenantName": target.get("microtenantName"),
                    } if target else planned_target,
                }
            )

        source_shares = _shared_to(source)
        target_shares = _shared_to(target) if target else []
        source_names = sorted(_stable(item.get("name")) for item in source_shares)
        target_names = sorted(_stable(item.get("name")) for item in target_shares)
        if source_names != target_names:
            details = source.get("sharedMicrotenantDetails") or {}
            shared_from = details.get("sharedFromMicrotenant") if isinstance(details, dict) else None
            missing_ids = [item for item in source_shares if item.get("id") is None]
            issue = ""
            if shared_from:
                issue = "an application shared from another Microtenant cannot manage sharing"
            elif missing_ids:
                issue = "one or more destination Microtenant IDs are missing"
            shares.append(
                {
                    "source": {
                        "id": source.get("id"),
                        "name": source.get("name"),
                        "shareToMicrotenants": [
                            item["id"] for item in source_shares if item.get("id") is not None
                        ],
                        "_issue": issue,
                    },
                    "target": {
                        "id": target.get("id"),
                        "name": target.get("name"),
                        "sharedMicrotenantDetails": target.get("sharedMicrotenantDetails"),
                    } if target else planned_target,
                }
            )

    empty = {"to_create": [], "to_delete": [], "unchanged": []}
    return {
        "application_segment_moves": {**empty, "to_update": moves},
        "application_segment_shares": {**empty, "to_update": shares},
    }


def application_move_path(customer_id: str, application_id: Any) -> str:
    return MOVE_APPLICATION.path.format(customer_id=customer_id, id=application_id)


def application_share_path(customer_id: str, application_id: Any) -> str:
    return SHARE_APPLICATION.path.format(customer_id=customer_id, id=application_id)


__all__ = [
    "PLACEMENT_FIELDS",
    "SPEC",
    "application_move_path",
    "application_share_path",
    "special_operation_sections",
]
