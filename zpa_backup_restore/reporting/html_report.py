"""Redacted HTML reports for backup, diff, and restore runs."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from zpa_backup_restore.core.catalog import (
    COVERAGE_RESOURCES,
    MIGRATION_ORDER,
    READ_ONLY_REFERENCE_RESOURCES,
    RESOURCES,
)
from zpa_backup_restore.core.diff import SPECIAL_DIFF_RESOURCES
from zpa_backup_restore.security import SENSITIVE_MARKERS, is_sensitive_key, redact


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def json_block(value: Any) -> str:
    return esc(json.dumps(redact(value), indent=2, ensure_ascii=False))


def resource_count(backup: dict[str, Any], key: str) -> str:
    value = backup.get("resources", {}).get(key)
    if value is None:
        return "failed"
    if isinstance(value, (list, dict)):
        return str(len(value))
    return "1" if value else "0"


def changed_names(section: dict[str, Any], item_key: str) -> list[str]:
    names = []
    for item in section.get(item_key, []) or []:
        obj = item.get("source", {}) if item_key == "to_update" else item
        names.append(str(obj.get("name") or obj.get("id") or "(unnamed)"))
    return names


def render_details(title: str, items: list[Any]) -> str:
    if not items:
        return ""
    chunks = [f"<details><summary>{esc(title)} ({len(items)})</summary>"]
    chunks.extend(f"<pre>{json_block(item)}</pre>" for item in items)
    chunks.append("</details>")
    return "\n".join(chunks)


def render_backup_section(label: str, backup: dict[str, Any] | None) -> str:
    if not backup:
        return ""
    meta = backup.get("meta", {})
    manifest = backup.get("manifest", {}) if isinstance(backup.get("manifest"), dict) else {}
    keys = [*RESOURCES, *READ_ONLY_REFERENCE_RESOURCES]
    rows = "".join(
        f"<tr><td>{esc(key)}</td><td>{esc(resource_count(backup, key))}</td></tr>" for key in keys
    )
    errors = backup.get("errors", {}) or {}
    error_html = ""
    if errors:
        error_rows = "".join(f"<tr><td>{esc(key)}</td><td>{esc(value)}</td></tr>" for key, value in errors.items())
        error_html = f"<h3>Backup Errors</h3><table>{error_rows}</table>"
    return f"""
<section>
  <h2>{esc(label)} Backup</h2>
  <p><strong>Tenant:</strong> {esc(meta.get('customerId', ''))} <strong>Timestamp:</strong> {esc(meta.get('timestamp', ''))}</p>
  <p><strong>Schema:</strong> {esc(manifest.get('schemaVersion', 'none'))} <strong>SHA-256:</strong> {esc(manifest.get('sha256', 'missing'))} <strong>Endpoint errors:</strong> {esc(manifest.get('errorCount', len(errors)))}</p>
  <table><thead><tr><th>Resource</th><th>Count</th></tr></thead><tbody>{rows}</tbody></table>
  {error_html}
</section>
"""


def render_diff_section(diff: dict[str, Any] | None) -> str:
    if not diff:
        return ""
    scope = diff.get("scope")
    scope_html = ""
    if isinstance(scope, dict):
        selector_rows = "".join(
            "<tr>"
            f"<td>{esc(item.get('selector', ''))}</td>"
            f"<td>{esc(item.get('displayName', ''))}</td>"
            f"<td>{esc(item.get('reason', ''))}</td>"
            "</tr>"
            for item in scope.get("resolvedSelectors", []) or []
            if isinstance(item, dict)
        )
        scope_html = f"""
  <h3>Selective Restore Scope</h3>
  <p>
    <strong>Dependencies:</strong> {esc('included' if scope.get('includeDependencies') else 'validate-only')}
    <strong>Policy order:</strong> {esc(scope.get('policyOrder', 'preserve-target'))}
  </p>
  <table><thead><tr><th>Selector</th><th>Name</th><th>Reason</th></tr></thead><tbody>{selector_rows}</tbody></table>
"""
    rows = []
    details = []
    for key in (*MIGRATION_ORDER, *SPECIAL_DIFF_RESOURCES):
        if key not in diff.get("resources", {}):
            continue
        summary = diff.get("summary", {}).get(key, {})
        section = diff.get("resources", {}).get(key, {})
        rows.append(
            "<tr>"
            f"<td>{esc(key)}</td><td>{esc(summary.get('create', 0))}</td>"
            f"<td>{esc(summary.get('update', 0))}</td><td>{esc(summary.get('delete', 0))}</td>"
            f"<td>{esc(summary.get('unchanged', 0))}</td></tr>"
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
  {scope_html}
  <table><thead><tr><th>Resource</th><th>Create</th><th>Update</th><th>Delete</th><th>Unchanged</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  <h2>Change Details</h2>{''.join(details) if details else '<p>No changes.</p>'}
</section>
"""


def render_apply_section(apply_result: dict[str, Any] | None) -> str:
    if not apply_result:
        return ""
    if apply_result.get("kind") == "restore-simulation":
        return render_simulation_section(apply_result)
    rows = "".join(
        "<tr>"
        f"<td>{esc(entry.get('action', ''))}</td><td>{esc(entry.get('resource', ''))}</td>"
        f"<td>{esc(entry.get('status', ''))}</td><td>{esc(entry.get('name', ''))}</td>"
        f"<td>{esc(entry.get('detail', ''))}</td></tr>"
        for entry in apply_result.get("log", []) or []
    )
    return f"""
<section><h2>Apply Result</h2>
  <p><strong>OK:</strong> {esc(apply_result.get('ok', 0))} <strong>Dry:</strong> {esc(apply_result.get('dry', 0))} <strong>Skipped:</strong> {esc(apply_result.get('skipped', 0))} <strong>Errors:</strong> {esc(apply_result.get('errors', 0))}</p>
  <table><thead><tr><th>Action</th><th>Resource</th><th>Status</th><th>Name</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""


def render_simulation_section(simulation: dict[str, Any]) -> str:
    summary = simulation.get("summary", {})
    safeguards = simulation.get("safeguards", {})
    assurance = simulation.get("assurance", {})
    scope = simulation.get("scope")
    rows = []
    details = []
    for operation in simulation.get("operations", []) or []:
        request = operation.get("request") or {}
        request_label = ""
        if request:
            request_label = f"{request.get('method', '')} {request.get('path', '')}".strip()
        rows.append(
            "<tr>"
            f"<td>{esc(operation.get('sequence', ''))}</td>"
            f"<td>{esc(operation.get('action', ''))}</td>"
            f"<td>{esc(operation.get('resource', ''))}</td>"
            f"<td>{esc(operation.get('status', ''))}</td>"
            f"<td>{esc(operation.get('name', ''))}</td>"
            f"<td>{esc(request_label)}</td>"
            f"<td>{esc(operation.get('payloadStatus', 'none'))}</td>"
            f"<td>{esc(operation.get('reason', ''))}</td>"
            "</tr>"
        )
        detail_parts = [
            f"<p><strong>Status:</strong> {esc(operation.get('status', ''))} "
            f"<strong>Dependencies:</strong> {esc(', '.join(operation.get('dependencies', [])))}</p>"
        ]
        if request:
            detail_parts.append(f"<p><strong>Request:</strong> {esc(request_label)}</p>")
            if request.get("body") is not None:
                detail_parts.append(f"<pre>{json_block(request['body'])}</pre>")
        if operation.get("deferredReferences"):
            detail_parts.append(
                render_details("Deferred references", operation["deferredReferences"])
            )
        if operation.get("unresolvedReferences"):
            detail_parts.append(
                render_details("Unresolved references", operation["unresolvedReferences"])
            )
        details.append(
            f"<details><summary>#{esc(operation.get('sequence', ''))} "
            f"{esc(operation.get('action', ''))} {esc(operation.get('resource', ''))}: "
            f"{esc(operation.get('name', ''))}</summary>{''.join(detail_parts)}</details>"
        )

    skip_reasons = simulation.get("skipReasons", {}) or {}
    skip_html = ""
    if skip_reasons:
        skip_html = "<h3>Skipped By Reason</h3><ul>" + "".join(
            f"<li>{esc(reason)}: {esc(count)}</li>" for reason, count in skip_reasons.items()
        ) + "</ul>"
    blocking_html = (
        f"<p class=\"danger\"><strong>Restore blocked:</strong> "
        f"{esc(summary.get('blocked', 0))} operation(s) require attention.</p>"
        if simulation.get("hasBlockingIssues")
        else "<p class=\"success\"><strong>No blocking simulation issues.</strong></p>"
    )
    assurance_html = ""
    if assurance:
        assurance_html = f"""
  <h3>Restore Assurance</h3>
  <table><tbody>
    <tr><th>Source backup SHA-256</th><td>{esc(assurance.get('sourceBackupSha256', ''))}</td></tr>
    <tr><th>Reviewed target SHA-256</th><td>{esc(assurance.get('targetBackupSha256', ''))}</td></tr>
    <tr><th>Diff SHA-256</th><td>{esc(assurance.get('diffSha256', ''))}</td></tr>
    <tr><th>Normalized target state SHA-256</th><td>{esc(assurance.get('targetStateSha256', ''))}</td></tr>
    <tr><th>Ordered plan SHA-256</th><td>{esc(assurance.get('planSha256', ''))}</td></tr>
  </tbody></table>
"""
    scope_html = ""
    if isinstance(scope, dict):
        scope_html = (
            "<p><strong>Selective scope:</strong> "
            f"{esc(len(scope.get('resolvedSelectors', []) or []))} object(s); "
            f"dependencies={esc('included' if scope.get('includeDependencies') else 'validate-only')}; "
            f"policy-order={esc(scope.get('policyOrder', 'preserve-target'))}</p>"
        )
    return f"""
<section>
  <h2>Restore Simulation</h2>
  {blocking_html}
  {scope_html}
  <p>
    <strong>Planned:</strong> {esc(summary.get('planned', 0))}
    <strong>Skipped:</strong> {esc(summary.get('skipped', 0))}
    <strong>Blocked:</strong> {esc(summary.get('blocked', 0))}
    <strong>Deferred operations:</strong> {esc(summary.get('deferredOperations', 0))}
    <strong>Unresolved references:</strong> {esc(summary.get('unresolvedReferences', 0))}
  </p>
  <p>
    <strong>Deletes:</strong> {esc('enabled' if safeguards.get('allowDelete') else 'disabled')}
    <strong>High-impact writes:</strong> {esc('enabled' if safeguards.get('allowHighImpact') else 'disabled')}
  </p>
  {assurance_html}
  {skip_html}
  <table><thead><tr><th>#</th><th>Action</th><th>Resource</th><th>Status</th><th>Name</th><th>Request</th><th>Payload</th><th>Reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  <h3>Ordered Request Details</h3>
  {''.join(details) if details else '<p>No operations.</p>'}
</section>
"""


def render_coverage_section() -> str:
    def operation_labels(meta: dict[str, Any]) -> str:
        return ", ".join(
            operation["key"]
            if operation.get("support", "enabled") == "enabled"
            else f"{operation['key']} [{operation['support']}]"
            for operation in meta.get("operations", [])
        )

    rows = "".join(
        "<tr>"
        f"<td>{esc(key)}</td><td>{esc(meta.get('mode', 'clone' if meta.get('writable') else 'reference'))}</td>"
        f"<td>{esc(meta.get('sensitivity', 'normal'))}</td>"
        f"<td>{esc(operation_labels(meta))}</td>"
        f"<td>{esc(meta.get('operation_source', 'compatibility'))}</td>"
        f"<td>{esc(meta.get('path', ''))}</td><td>{esc(', '.join(meta.get('depends_on', [])))}</td>"
        f"<td>{esc(meta.get('notes', ''))}</td></tr>"
        for key, meta in COVERAGE_RESOURCES.items()
    )
    return f"<section><h2>Coverage</h2><table><thead><tr><th>Resource</th><th>Mode</th><th>Sensitivity</th><th>Operations</th><th>Source</th><th>Endpoint</th><th>Dependencies</th><th>Notes</th></tr></thead><tbody>{rows}</tbody></table></section>"


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
<html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 28px; color: #1f2933; }}
h1 {{ font-size: 28px; margin-bottom: 4px; }} h2 {{ font-size: 20px; margin-top: 28px; border-bottom: 1px solid #d9e2ec; padding-bottom: 6px; }} h3 {{ font-size: 16px; margin-top: 18px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0 18px; }} th, td {{ border: 1px solid #d9e2ec; padding: 7px 9px; text-align: left; vertical-align: top; font-size: 13px; }} th {{ background: #f4f7fb; }}
pre {{ background: #0f172a; color: #e2e8f0; padding: 12px; overflow-x: auto; border-radius: 6px; font-size: 12px; }} details {{ margin: 8px 0; }} summary {{ cursor: pointer; font-weight: 600; }} .muted {{ color: #627d98; }}
.danger {{ color: #b42318; }} .success {{ color: #067647; }}
</style></head><body>
<h1>{esc(title)}</h1><p class="muted">Sensitive-looking values are redacted in this report.</p>
{render_backup_section('Source', source_backup)}{render_backup_section('Target', target_backup)}
{render_diff_section(diff)}{render_apply_section(apply_result)}
{render_coverage_section() if include_coverage else ''}
</body></html>"""


def write_report(path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(**kwargs), encoding="utf-8")
    return path
