"""Persistence contract for the run-level audit ledger."""

from __future__ import annotations

from typing import Any, Protocol

from zpa_backup_restore.domain.models import LedgerVerification


class RunAuditLedger(Protocol):
    def append(self, *, run_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]: ...

    def read_events(self) -> list[dict[str, Any]]: ...

    def verify(self) -> LedgerVerification: ...


__all__ = ["RunAuditLedger"]
