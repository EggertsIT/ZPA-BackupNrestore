"""Typed models used by every ZPA resource and API-operation module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """One documented ZPA HTTP operation.

    Operation declarations are deliberately data-only. Shared services remain
    responsible for authentication, pagination, audit logging, redaction, and
    guarded execution.
    """

    key: str
    method: str
    path: str
    role: str
    pagination: str = "none"
    documentation_slug: str = ""
    high_impact: bool = False
    support: str = "enabled"
    notes: str = ""

    def __post_init__(self) -> None:
        method = self.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"Unsupported HTTP method for {self.key}: {self.method}")
        if self.pagination not in {"none", "page", "cursor"}:
            raise ValueError(f"Unsupported pagination for {self.key}: {self.pagination}")
        if self.support not in {"enabled", "catalog-only", "excluded"}:
            raise ValueError(f"Unsupported operation status for {self.key}: {self.support}")
        if not self.path.startswith("/"):
            raise ValueError(f"Operation path must be absolute for {self.key}: {self.path}")
        object.__setattr__(self, "method", method)

    @property
    def mutating(self) -> bool:
        return self.method != "GET"

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "method": self.method,
            "path": self.path,
            "role": self.role,
            "pagination": self.pagination,
            "documentation_slug": self.documentation_slug,
            "high_impact": self.high_impact,
            "support": self.support,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """Declarative API and restore behavior for one ZPA resource."""

    key: str
    path: str
    detail_path: str | None = None
    detail_strategy: str = "detail"
    id_field: str = "id"
    name_field: str = "name"
    writable: bool = True
    depends_on: tuple[str, ...] = ()
    skip_fields: frozenset[str] = field(default_factory=frozenset)
    notes: str = ""
    high_impact: bool = False
    mode: str = "clone"
    sensitivity: str = "normal"
    operations: tuple[OperationSpec, ...] = ()
    optional: bool = False
    backup_skip_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.mode not in {"clone", "reference", "audit", "excluded"}:
            raise ValueError(f"Unsupported coverage mode for {self.key}: {self.mode}")
        if self.sensitivity not in {"normal", "high-impact", "sensitive", "secret"}:
            raise ValueError(f"Unsupported sensitivity for {self.key}: {self.sensitivity}")
        operation_keys = [operation.key for operation in self.operations]
        if len(operation_keys) != len(set(operation_keys)):
            raise ValueError(f"Duplicate API operation for {self.key}")
        if not self.writable and any(
            operation.mutating and operation.support == "enabled"
            for operation in self.operations
        ):
            raise ValueError(f"Read-only resource {self.key} declares a mutating operation")

    @property
    def actions(self) -> tuple[str, ...]:
        """Explicit actions, with a compatibility fallback during migration."""
        if self.operations:
            return tuple(operation.key for operation in self.operations)
        return ("list", "get", "create", "update", "delete") if self.writable else ("list", "get")

    @property
    def enabled_actions(self) -> tuple[str, ...]:
        if self.operations:
            return tuple(
                operation.key
                for operation in self.operations
                if operation.support == "enabled"
            )
        return self.actions

    def as_legacy_dict(self) -> dict:
        """Expose the v1 dictionary shape during the compatibility window."""
        list_operation = next(
            (operation for operation in self.operations if operation.role == "list"),
            None,
        )
        return {
            "path": self.path,
            "detail_path": self.detail_path,
            "detail_strategy": self.detail_strategy,
            "id_field": self.id_field,
            "name_field": self.name_field,
            "writable": self.writable,
            "depends_on": list(self.depends_on),
            "skip_fields": set(self.skip_fields),
            "notes": self.notes,
            "high_impact": self.high_impact,
            "mode": self.mode,
            "sensitivity": self.sensitivity,
            "actions": list(self.actions),
            "enabled_actions": list(self.enabled_actions),
            "operations": [operation.as_dict() for operation in self.operations],
            "optional": self.optional,
            "backup_skip_fields": set(self.backup_skip_fields),
            "pagination": list_operation.pagination if list_operation else "page",
            "operation_source": "explicit" if self.operations else "compatibility",
            **{
                f"{role}_path": operation.path
                for role in ("create", "update", "delete")
                if (
                    operation := next(
                        (
                            candidate
                            for candidate in self.operations
                            if candidate.role == role and candidate.support == "enabled"
                        ),
                        None,
                    )
                )
            },
            **{
                f"{role}_method": operation.method
                for role in ("create", "update", "delete")
                if (
                    operation := next(
                        (
                            candidate
                            for candidate in self.operations
                            if candidate.role == role and candidate.support == "enabled"
                        ),
                        None,
                    )
                )
            },
        }


def operation(
    key: str,
    method: str,
    path: str,
    *,
    role: str | None = None,
    pagination: str = "none",
    documentation_slug: str = "",
    high_impact: bool = False,
    support: str = "enabled",
    notes: str = "",
) -> OperationSpec:
    """Concise constructor used by declarative operation modules."""
    return OperationSpec(
        key=key,
        method=method,
        path=path,
        role=role or key,
        pagination=pagination,
        documentation_slug=documentation_slug,
        high_impact=high_impact,
        support=support,
        notes=notes,
    )


__all__ = ["OperationSpec", "ResourceSpec", "operation"]
