"""Cross-tenant ID remapping seeded from stable resource names."""

from __future__ import annotations

from typing import Any

from zpa_backup_restore.core.catalog import RESOURCES
from zpa_backup_restore.core.diff import identity_key, normalize_name


class IDMapper:
    def __init__(self) -> None:
        self.map: dict[str, str] = {}

    def add(self, source_id: Any, target_id: Any) -> None:
        if source_id is not None and target_id is not None:
            self.map[str(source_id)] = str(target_id)

    def lookup(self, value: Any) -> Any:
        if isinstance(value, (str, int)):
            return self.map.get(str(value), value)
        return value

    def remap(self, obj: Any, *, root: bool = True) -> Any:
        if isinstance(obj, list):
            return [self.remap(item, root=False) for item in obj]
        if not isinstance(obj, dict):
            return self.lookup(obj)
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "id" and root:
                out[key] = value
            elif key in {"id", "idpId", "policySetId", "_policySetId", "lhs", "rhs"}:
                out[key] = self.lookup(value)
            else:
                out[key] = self.remap(value, root=False)
        return out


def ref_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("displayName") or item.get("id") or "")


def seed_by_name(
    mapper: IDMapper,
    src_items: list[dict[str, Any]],
    tgt_items: list[dict[str, Any]],
    name_field: str,
) -> None:
    targets = {identity_key(item, name_field): item for item in tgt_items if isinstance(item, dict)}
    for source in src_items:
        target = targets.get(identity_key(source, name_field))
        if target:
            mapper.add(source.get("id"), target.get("id"))


def seed_identity_refs(mapper: IDMapper, src_backup: dict[str, Any], tgt_backup: dict[str, Any]) -> None:
    src_res = src_backup.get("resources", {})
    tgt_res = tgt_backup.get("resources", {})
    seed_by_name(mapper, src_res.get("idps", []) or [], tgt_res.get("idps", []) or [], "name")

    def scoped_key(item: dict[str, Any]) -> str:
        return f"{normalize_name(item.get('_idpName'))}:{normalize_name(ref_name(item))}"

    for key in ("saml_attributes", "scim_attributes", "scim_groups"):
        targets = {scoped_key(item): item for item in tgt_res.get(key, []) or [] if isinstance(item, dict)}
        for source in src_res.get(key, []) or []:
            if isinstance(source, dict) and (target := targets.get(scoped_key(source))):
                mapper.add(source.get("id"), target.get("id"))

    for key, meta in RESOURCES.items():
        if not meta.get("writable"):
            seed_by_name(
                mapper,
                src_res.get(key, []) or [],
                tgt_res.get(key, []) or [],
                meta["name_field"],
            )


__all__ = ["IDMapper", "ref_name", "seed_by_name", "seed_identity_refs"]
