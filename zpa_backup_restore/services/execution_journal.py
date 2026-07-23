"""Crash-visible per-operation restore execution journal."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from zpa_backup_restore.core.integrity import canonical_json
from zpa_backup_restore.security import redact


EXECUTION_JOURNAL_SCHEMA_VERSION = "1.0"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _operation_id(
    *,
    action: str,
    resource: str,
    name: str,
    source_id: Any | None,
    target_id: Any | None,
) -> str:
    material = {
        "action": action,
        "resource": resource,
        "name": name,
        "sourceId": source_id,
        "targetId": target_id,
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


class FileExecutionJournal:
    """Atomically persists operation state before and after each destination call."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        plan_sha256: str,
        scope: dict[str, Any] | None = None,
    ) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.document: dict[str, Any] = {
            "kind": "restore-execution-journal",
            "schemaVersion": EXECUTION_JOURNAL_SCHEMA_VERSION,
            "runId": run_id,
            "planSha256": plan_sha256,
            "scope": scope,
            "createdAt": _now(),
            "updatedAt": _now(),
            "operations": {},
        }
        self._persist()

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(redact(self.document), indent=2, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _identity(
        *,
        action: str,
        resource: str,
        name: str,
        source_id: Any | None,
        target_id: Any | None,
    ) -> tuple[str, dict[str, Any]]:
        operation = {
            "action": action,
            "resource": resource,
            "name": name,
            "sourceId": source_id,
            "targetId": target_id,
        }
        return _operation_id(
            action=action,
            resource=resource,
            name=name,
            source_id=source_id,
            target_id=target_id,
        ), operation

    def begin(
        self,
        *,
        action: str,
        resource: str,
        name: str,
        source_id: Any | None,
        target_id: Any | None,
    ) -> None:
        operation_id, operation = self._identity(
            action=action,
            resource=resource,
            name=name,
            source_id=source_id,
            target_id=target_id,
        )
        with self.lock:
            self.document["operations"][operation_id] = {
                **operation,
                "status": "running",
                "startedAt": _now(),
                "finishedAt": "",
                "detail": "",
                "createdTargetId": None,
            }
            self.document["updatedAt"] = _now()
            self._persist()

    def finish(
        self,
        *,
        action: str,
        resource: str,
        name: str,
        source_id: Any | None,
        target_id: Any | None,
        status: str,
        detail: str,
        created_target_id: Any | None = None,
    ) -> None:
        operation_id, operation = self._identity(
            action=action,
            resource=resource,
            name=name,
            source_id=source_id,
            target_id=target_id,
        )
        with self.lock:
            existing = self.document["operations"].get(operation_id, {})
            self.document["operations"][operation_id] = {
                **operation,
                "status": status,
                "startedAt": existing.get("startedAt", ""),
                "finishedAt": _now(),
                "detail": detail,
                "createdTargetId": created_target_id,
            }
            self.document["updatedAt"] = _now()
            self._persist()


__all__ = ["EXECUTION_JOURNAL_SCHEMA_VERSION", "FileExecutionJournal"]
