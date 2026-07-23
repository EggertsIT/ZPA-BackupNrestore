"""Append-only, hash-chained JSONL run ledger with a separate head checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from zpa_backup_restore.core.integrity import canonical_json
from zpa_backup_restore.domain.models import LedgerVerification
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.security import redact

try:  # macOS/Linux process coordination; writes remain safe without it on other platforms.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


AUDIT_LEDGER_SCHEMA_VERSION = 1
DEFAULT_RUN_LEDGER_PATH = Path("logs/run-ledger.jsonl")


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _event_hash(event_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event_without_hash).encode("utf-8")).hexdigest()


class JsonlRunAuditLedger:
    """Tamper-evident ledger; it is not a cryptographic signature or tamper-proof store."""

    def __init__(self, path: Path = DEFAULT_RUN_LEDGER_PATH, *, clock: Callable[[], str] = _utc_now) -> None:
        self.path = path
        self.head_path = path.with_name(path.name + ".head")
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _lock(handle: Any, *, exclusive: bool) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)

    @staticmethod
    def _unlock(handle: Any) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_checkpoint(self) -> dict[str, Any] | None:
        if not self.head_path.is_file():
            return None
        try:
            value = json.loads(self.head_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CliError(f"Cannot read audit ledger checkpoint {self.head_path}: {error}") from error
        return value if isinstance(value, dict) else None

    def _write_checkpoint(self, *, event_count: int, head_hash: str) -> None:
        payload = {
            "schemaVersion": AUDIT_LEDGER_SCHEMA_VERSION,
            "eventCount": event_count,
            "headHash": head_hash,
        }
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{self.head_path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.head_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def _parse(self, text: str) -> tuple[list[dict[str, Any]], list[str]]:
        events: list[dict[str, Any]] = []
        errors: list[str] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                errors.append(f"line {line_number}: invalid JSON ({error.msg})")
                continue
            if not isinstance(event, dict):
                errors.append(f"line {line_number}: event must be an object")
                continue
            events.append(event)
        return events, errors

    def _verify_events(
        self,
        events: list[dict[str, Any]],
        parse_errors: list[str],
        *,
        check_checkpoint: bool,
    ) -> LedgerVerification:
        errors = list(parse_errors)
        previous_hash = "0" * 64
        run_ids: set[str] = set()
        for index, event in enumerate(events, start=1):
            if event.get("schemaVersion") != AUDIT_LEDGER_SCHEMA_VERSION:
                errors.append(f"event {index}: unsupported schema version")
            if event.get("sequence") != index:
                errors.append(f"event {index}: sequence mismatch")
            if event.get("previousHash") != previous_hash:
                errors.append(f"event {index}: previous hash mismatch")
            supplied_hash = event.get("eventHash")
            unsigned = dict(event)
            unsigned.pop("eventHash", None)
            calculated_hash = _event_hash(unsigned)
            if supplied_hash != calculated_hash:
                errors.append(f"event {index}: event hash mismatch")
            previous_hash = str(supplied_hash or calculated_hash)
            if event.get("runId"):
                run_ids.add(str(event["runId"]))

        if check_checkpoint:
            checkpoint = self._read_checkpoint()
            if events and checkpoint is None:
                errors.append("ledger head checkpoint is missing")
            elif checkpoint is not None:
                if checkpoint.get("eventCount") != len(events):
                    errors.append("ledger event count does not match head checkpoint")
                if checkpoint.get("headHash") != previous_hash:
                    errors.append("ledger hash does not match head checkpoint")
                if checkpoint.get("schemaVersion") != AUDIT_LEDGER_SCHEMA_VERSION:
                    errors.append("ledger head checkpoint schema is unsupported")
        return LedgerVerification(
            valid=not errors,
            event_count=len(events),
            run_count=len(run_ids),
            head_hash=previous_hash if events else "",
            errors=tuple(errors),
        )

    def append(self, *, run_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        if not run_id or not event_type:
            raise CliError("Audit ledger events require a run ID and event type")
        with self.path.open("a+", encoding="utf-8") as handle:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._lock(handle, exclusive=True)
            try:
                handle.seek(0)
                events, parse_errors = self._parse(handle.read())
                verification = self._verify_events(events, parse_errors, check_checkpoint=True)
                if not verification.valid:
                    raise CliError(
                        "Refusing to append to an invalid audit ledger:\n"
                        + "\n".join(f"- {error}" for error in verification.errors)
                    )
                previous_hash = events[-1]["eventHash"] if events else "0" * 64
                event = {
                    "schemaVersion": AUDIT_LEDGER_SCHEMA_VERSION,
                    "sequence": len(events) + 1,
                    "timestamp": self.clock(),
                    "runId": run_id,
                    "type": event_type,
                    "data": redact(data),
                    "previousHash": previous_hash,
                }
                event["eventHash"] = _event_hash(event)
                handle.seek(0, os.SEEK_END)
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                self._write_checkpoint(event_count=len(events) + 1, head_hash=event["eventHash"])
                return event
            finally:
                self._unlock(handle)

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            self._lock(handle, exclusive=False)
            try:
                events, errors = self._parse(handle.read())
            finally:
                self._unlock(handle)
        if errors:
            raise CliError("Audit ledger contains invalid JSON:\n" + "\n".join(f"- {e}" for e in errors))
        return events

    def verify(self) -> LedgerVerification:
        if not self.path.is_file():
            checkpoint = self._read_checkpoint()
            errors = ("ledger file is missing but a head checkpoint exists",) if checkpoint else ()
            return LedgerVerification(not errors, 0, 0, "", errors)
        with self.path.open("r", encoding="utf-8") as handle:
            self._lock(handle, exclusive=False)
            try:
                events, errors = self._parse(handle.read())
                return self._verify_events(events, errors, check_checkpoint=True)
            finally:
                self._unlock(handle)


__all__ = [
    "AUDIT_LEDGER_SCHEMA_VERSION",
    "DEFAULT_RUN_LEDGER_PATH",
    "JsonlRunAuditLedger",
]
