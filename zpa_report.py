"""HTML report generation for ZPA backup, diff, and restore runs."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from zpa_resources import MIGRATION_ORDER, READ_ONLY_REFERENCE_RESOURCES, RESOURCES


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


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def is_sensitive_key(key: str) -> bool:
    compact = key.replace("-", "").replace("_", "").casefold()
    return any(marker.replace("_", "") in compact for marker in SENSITIVE_MARKERS)


def redact(value: Any, key_name: str = "") -> Any:
    if key_name and is_sensitive_key(key_name):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {key: redact(child, key) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child, key_name) for child in value]
    return value


def json_block(value: Any) -> str:
    return esc(json.dumps(redact(value), indent=2, ensure_ascii=False))


def resource_count(backup: dict[str, Any], key: str) -> str:
    value = backup.get("resources", {}).get(key)
    if value is None:
        return "failed"
    if isinstance(value, list):
        return str(len(value))
    if isinstance(value, dict):
        return str(len(value))
    return "1" if value else "0"


def changed_names(section: dict[str, Any], item_key: str) -> list[str]:
    names = []
    for item in section.get(item_key, []) or []:
        if item_key == "to_update":
            obj = item.get("source", {})
        else:
            obj = item
        names.append(str(obj.get("name") or obj.get("id") or "(unnamed)"))
    return names


def render_details(title: str, items: list[Any]) -> str:
    if not items:
        return ""
    chunks = [f"<details><summary>{esc(title)} ({len(items)})</summary>"]
    for item in items:
        chunks.append(f"<pre>{json_block(item)}</pre>")
    chunks.append("</details>")
    return "\n".join(chunks)


def render_backup_section(label: str, backup: dict[str, Any] | None) -> str:
    if not backup:
        return ""
    meta = backup.get("meta", {})
    manifest = backup.get("manifest", {}) if isinstance(backup.get("manifest"), dict) else {}
    rows = []
    for key in RESOURCES:
        rows.append(f"<tr><td>{esc(key)}</td><td>{esc(resource_count(backup, key))}</td></tr>")
    for key in READ_ONLY_REFERENCE_RESOURCES:
        rows.append(f"<tr><td>{esc(key)}</td><td>{esc(resource_count(backup, key))}</td></tr>")
    errors = backup.get("errors", {}) or {}
    error_html = ""
    if errors:
        error_rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in errors.items())
        error_html = f"<h3>Backup Errors</h3><table>{error_rows}</table>"
    return f"""
<section>
  <h2>{esc(label)} Backup</h2>
  <p><strong>Tenant:</strong> {esc(meta.get("customerId", ""))} <strong>Timestamp:</strong> {esc(meta.get("timestamp", ""))}</p>
  <p>
    <strong>Schema:</strong> {esc(manifest.get("schemaVersion", "none"))}
    <strong>SHA-256:</strong> {esc(manifest.get("sha256", "missing"))}
    <strong>Endpoint errors:</strong> {esc(manifest.get("errorCount", len(errors)))}
  </p>
  <table>
    <thead><tr><th>Resource</th><th>Count</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {error_html}
</section>
"""


def render_diff_section(diff: dict[str, Any] | None) -> str:
    if not diff:
        return ""
    rows = []
    details = []
    for key in MIGRATION_ORDER:
        summary = diff.get("summary", {}).get(key, {})
        section = diff.get("resources", {}).get(key, {})
        rows.append(
            "<tr>"
            f"<td>{esc(key)}</td>"
            f"<td>{esc(summary.get('create', 0))}</td>"
            f"<td>{esc(summary.get('update', 0))}</td>"
            f"<td>{esc(summary.get('delete', 0))}</td>"
            f"<td>{esc(summary.get('unchanged', 0))}</td>"
            "</tr>"
        )
        names = []
        for label, item_key in (("Create", "to_create"), ("Update", "to_update"), ("Delete", "to_delete")):
            current = changed_names(section, item_key)
            if current:
                names.append(f"<p><strong>{esc(label)}:</strong> {esc(', '.join(current))}</p>")
        if names:
            details.append(f"<h3>{esc(key)}</h3>{''.join(names)}")
            details.append(render_details("Create payloads", section.get("to_create", [])))
            details.append(render_details("Update payloads", section.get("to_update", [])))
            details.append(render_details("Delete payloads", section.get("to_delete", [])))
    return f"""
<section>
  <h2>Diff Summary</h2>
  <table>
    <thead><tr><th>Resource</th><th>Create</th><th>Update</th><th>Delete</th><th>Unchanged</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>Change Details</h2>
  {''.join(details) if details else '<p>No changes.</p>'}
</section>
"""


def render_apply_section(apply_result: dict[str, Any] | None) -> str:
    if not apply_result:
        return ""
    rows = []
    for entry in apply_result.get("log", []) or []:
        rows.append(
            "<tr>"
            f"<td>{esc(entry.get('action', ''))}</td>"
            f"<td>{esc(entry.get('resource', ''))}</td>"
            f"<td>{esc(entry.get('status', ''))}</td>"
            f"<td>{esc(entry.get('name', ''))}</td>"
            f"<td>{esc(entry.get('detail', ''))}</td>"
            "</tr>"
        )
    return f"""
<section>
  <h2>Apply Result</h2>
  <p>
    <strong>OK:</strong> {esc(apply_result.get("ok", 0))}
    <strong>Dry:</strong> {esc(apply_result.get("dry", 0))}
    <strong>Skipped:</strong> {esc(apply_result.get("skipped", 0))}
    <strong>Errors:</strong> {esc(apply_result.get("errors", 0))}
  </p>
  <table>
    <thead><tr><th>Action</th><th>Resource</th><th>Status</th><th>Name</th><th>Detail</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def render_coverage_section() -> str:
    rows = []
    for key, meta in RESOURCES.items():
        rows.append(
            "<tr>"
            f"<td>{esc(key)}</td>"
            f"<td>{esc('write' if meta.get('writable') else 'read')}</td>"
            f"<td>{esc(meta.get('path', ''))}</td>"
            f"<td>{esc(', '.join(meta.get('depends_on', [])))}</td>"
            f"<td>{esc(meta.get('notes', ''))}</td>"
            "</tr>"
        )
    return f"""
<section>
  <h2>Coverage</h2>
  <table>
    <thead><tr><th>Resource</th><th>Mode</th><th>Endpoint</th><th>Dependencies</th><th>Notes</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def render_report(
    *,
    title: str,
    source_backup: dict[str, Any] | None = None,
    target_backup: dict[str, Any] | None = None,
    diff: dict[str, Any] | None = None,
    apply_result: dict[str, Any] | None = None,
    include_coverage: bool = True,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{esc(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 28px; color: #1f2933; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 20px; margin-top: 28px; border-bottom: 1px solid #d9e2ec; padding-bottom: 6px; }}
    h3 {{ font-size: 16px; margin-top: 18px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 18px; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 7px 9px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f4f7fb; }}
    pre {{ background: #0f172a; color: #e2e8f0; padding: 12px; overflow-x: auto; border-radius: 6px; font-size: 12px; }}
    details {{ margin: 8px 0; }}
    summary {{ cursor: pointer; font-weight: 600; }}
    .muted {{ color: #627d98; }}
  </style>
</head>
<body>
  <h1>{esc(title)}</h1>
  <p class="muted">Sensitive-looking values are redacted in this report.</p>
  {render_backup_section("Source", source_backup)}
  {render_backup_section("Target", target_backup)}
  {render_diff_section(diff)}
  {render_apply_section(apply_result)}
  {render_coverage_section() if include_coverage else ""}
</body>
</html>
"""


def write_report(path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(**kwargs), encoding="utf-8")
    return path
