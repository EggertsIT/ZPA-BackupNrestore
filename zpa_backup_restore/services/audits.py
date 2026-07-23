"""Run-level audit queries independent of JSONL storage and CLI presentation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from zpa_backup_restore.errors import CliError
from zpa_backup_restore.repositories.audit import RunAuditLedger


class AuditService:
    def __init__(self, ledger: RunAuditLedger) -> None:
        self.ledger = ledger

    def list_runs(self, *, failures_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for event in self.ledger.read_events():
            grouped.setdefault(str(event.get("runId", "")), []).append(event)
        runs = [self._summarize(events) for events in grouped.values() if events]
        if failures_only:
            runs = [run for run in runs if run["status"] == "failed"]
        runs.sort(key=lambda run: (run["startedAt"], run["runId"]), reverse=True)
        return runs[: max(1, limit)]

    @staticmethod
    def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
        first = events[0]
        started = next((event for event in events if event.get("type") == "run.started"), first)
        finished = next(
            (event for event in reversed(events) if event.get("type") == "run.finished"),
            None,
        )
        start_data = started.get("data", {})
        finish_data = finished.get("data", {}) if finished else {}
        exit_code = finish_data.get("exitCode")
        status = "running" if finished is None else ("succeeded" if exit_code == 0 else "failed")
        artifacts = [event for event in events if event.get("type") == "artifact.recorded"]
        return {
            "runId": str(first.get("runId", "")),
            "command": str(start_data.get("command", "unknown")),
            "startedAt": str(started.get("timestamp", "")),
            "finishedAt": str(finished.get("timestamp", "")) if finished else "",
            "status": status,
            "exitCode": exit_code,
            "eventCount": len(events),
            "artifactCount": len(artifacts),
            "error": str(finish_data.get("error", "")),
        }

    def run_detail(self, identifier: str) -> dict[str, Any]:
        events = self.ledger.read_events()
        run_ids = sorted({str(event.get("runId", "")) for event in events})
        matches = [run_id for run_id in run_ids if run_id == identifier or run_id.startswith(identifier)]
        if len(matches) > 1:
            raise CliError(f"Audit run ID prefix is ambiguous: {identifier}")
        if not matches:
            raise CliError(f"Audit run not found: {identifier}")
        run_events = [event for event in events if event.get("runId") == matches[0]]
        return {"summary": self._summarize(run_events), "events": run_events}

    def command_summary(self) -> list[dict[str, Any]]:
        counts: dict[str, Counter[str]] = {}
        for run in self.list_runs(limit=1_000_000):
            counter = counts.setdefault(run["command"], Counter())
            counter["total"] += 1
            counter[run["status"]] += 1
        return [
            {
                "command": command,
                "total": counter["total"],
                "succeeded": counter["succeeded"],
                "failed": counter["failed"],
                "running": counter["running"],
            }
            for command, counter in sorted(counts.items())
        ]


__all__ = ["AuditService"]
