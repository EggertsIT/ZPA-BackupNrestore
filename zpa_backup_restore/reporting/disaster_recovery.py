"""Printable HTML rendering for disaster-recovery runbooks."""

from __future__ import annotations

import html
import os
import shlex
from collections import defaultdict
from pathlib import Path
from typing import Any

from zpa_backup_restore.security import redact
from zpa_backup_restore.services.disaster_recovery import (
    DR_COMPLETION_STATUSES,
    verify_disaster_recovery_runbook,
)


PHASE_LABELS = {
    "1-readiness": "1. Recovery Readiness",
    "2-authorization": "2. Authorization and Change Control",
    "3-settings": "3. Modeled Domains and Captured Settings",
    "4-external": "4. External and Intentionally Excluded Recovery",
    "5-verification": "5. Post-Restore Verification",
    "6-closure": "6. Recovery Closure",
}

CAPABILITY_LABELS = {
    "automated": "Guarded automated restore",
    "reference": "Destination reference verification",
    "protected-manual": "Protected manual recovery",
    "audit-only": "Operational audit validation",
    "external": "External/manual recovery",
}


def esc(value: Any) -> str:
    return html.escape(str(redact(value)), quote=True)


def _status_label(status: str) -> str:
    return status.replace("-", " ").title()


def _render_command(command: dict[str, str]) -> str:
    return (
        f"<div class=\"command\"><strong>{esc(command.get('label', 'Command'))}</strong>"
        f"<pre>{esc(command.get('command', ''))}</pre></div>"
    )


def _render_item(item: dict[str, Any], runbook_path: Path | None) -> str:
    status = str(item.get("status") or "pending")
    checked = " checked" if status in DR_COMPLETION_STATUSES else ""
    disabled = " disabled"
    dependencies = item.get("dependencies", []) or []
    instructions = "".join(
        f"<li>{esc(step)}</li>" for step in item.get("instructions", []) or []
    )
    commands = "".join(
        _render_command(command)
        for command in item.get("commands", []) or []
        if isinstance(command, dict)
    )
    metadata = [
        ("Item ID", item.get("id", "")),
        ("Category", item.get("category", "")),
        ("Capability", CAPABILITY_LABELS.get(str(item.get("capability")), item.get("capability", ""))),
        ("Risk", item.get("risk", "")),
    ]
    if item.get("resourceType"):
        metadata.extend(
            [
                ("Resource type", item.get("resourceType", "")),
                ("Stable identity", item.get("stableKey", "") or "domain-level"),
                ("Mode", item.get("mode", "")),
                ("Configuration SHA-256", item.get("sourceConfigSha256", "") or "not stored"),
            ]
        )
    if dependencies:
        metadata.append(("Dependencies/references", ", ".join(map(str, dependencies))))
    metadata_rows = "".join(
        f"<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>"
        for label, value in metadata
    )
    evidence = ""
    if any(item.get(field) for field in ("operator", "updatedAt", "evidence", "operatorNote")):
        evidence = f"""
<div class="evidence">
  <strong>Checklist evidence</strong>
  <dl>
    <dt>Operator</dt><dd>{esc(item.get('operator', ''))}</dd>
    <dt>Updated</dt><dd>{esc(item.get('updatedAt', ''))}</dd>
    <dt>Evidence</dt><dd>{esc(item.get('evidence', ''))}</dd>
    <dt>Note</dt><dd>{esc(item.get('operatorNote', ''))}</dd>
  </dl>
</div>
"""
    update_example = ""
    if runbook_path is not None:
        update_command = shlex.join(
            [
                "python3",
                "-m",
                "zpa_backup_restore",
                "dr",
                "check",
                "--runbook",
                str(runbook_path),
                "--item",
                str(item.get("id", "")),
                "--status",
                "completed",
                "--actor",
                "OPERATOR_NAME",
                "--evidence",
                "TICKET_OR_ARTIFACT_REFERENCE",
            ]
        )
        update_example = (
            "<p class=\"update\"><strong>Record completion:</strong></p>"
            f"<pre>{esc(update_command)}</pre>"
        )
    detail = (
        f"<p class=\"detail\">{esc(item.get('detail'))}</p>"
        if item.get("detail")
        else ""
    )
    gap = (
        '<span class="badge gap">Coverage gap / external evidence required</span>'
        if item.get("coverageGap")
        else ""
    )
    return f"""
<article class="item status-{esc(status)}">
  <header>
    <label><input type="checkbox"{checked}{disabled}> <span class="sequence">#{esc(item.get('sequence', ''))}</span> {esc(item.get('name', ''))}</label>
    <span class="badge status">{esc(_status_label(status))}</span>
    {gap}
  </header>
  {detail}
  <table class="metadata"><tbody>{metadata_rows}</tbody></table>
  <h4>Ordered recovery procedure</h4>
  <ol>{instructions}</ol>
  {commands}
  {evidence}
  {update_example}
</article>
"""


def _render_coverage(runbook: dict[str, Any]) -> str:
    coverage = runbook.get("coverage", {}) or {}
    rows = []
    for domain in coverage.get("domains", []) or []:
        counts = ", ".join(
            f"{key}={value}" for key, value in (domain.get("counts", {}) or {}).items()
        ) or "not captured"
        rows.append(
            "<tr>"
            f"<td>{esc(domain.get('resource', ''))}</td>"
            f"<td>{esc(domain.get('captureStatus', ''))}</td>"
            f"<td>{esc(domain.get('mode', ''))}</td>"
            f"<td>{esc(CAPABILITY_LABELS.get(str(domain.get('capability')), domain.get('capability', '')))}</td>"
            f"<td>{esc(counts)}</td>"
            f"<td>{esc(domain.get('notes', ''))}</td>"
            "</tr>"
        )
    return f"""
<section>
  <h2>Recovery Coverage Matrix</h2>
  <p>{esc(coverage.get('claim', ''))}</p>
  <p><strong>Modeled domains:</strong> {esc(coverage.get('modeledDomainCount', 0))}
     <strong>Explicit API operations:</strong> {esc(coverage.get('explicitOperationCount', 0))}</p>
  <table>
    <thead><tr><th>Domain</th><th>Capture</th><th>Mode</th><th>Recovery path</th><th>Counts</th><th>Boundary</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def render_disaster_recovery_report(
    runbook: dict[str, Any],
    *,
    runbook_path: Path | None = None,
) -> str:
    verification = verify_disaster_recovery_runbook(runbook, check_source=False)
    summary = runbook.get("summary", {}) or {}
    source = runbook.get("source", {}) or {}
    integrity = runbook.get("integrity", {}) or {}
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in runbook.get("items", []) or []:
        if isinstance(item, dict):
            grouped[str(item.get("phase") or "other")].append(item)
    phases = "".join(
        f"<section class=\"phase\"><h2>{esc(PHASE_LABELS.get(phase, phase))}</h2>"
        + "".join(_render_item(item, runbook_path) for item in grouped[phase])
        + "</section>"
        for phase in PHASE_LABELS
        if grouped.get(phase)
    )
    verification_banner = (
        '<p class="banner success"><strong>Runbook integrity verified.</strong></p>'
        if verification["valid"]
        else (
            '<p class="banner danger"><strong>Runbook integrity verification failed:</strong> '
            + esc("; ".join(verification["errors"]))
            + "</p>"
        )
    )
    backup_banner = (
        '<p class="banner danger"><strong>Recovery readiness blocked:</strong> '
        f"{esc(len(source.get('validationIssues', []) or []))} validation issue(s) and "
        f"{esc(len(source.get('endpointErrorKeys', []) or []))} endpoint error(s) are recorded.</p>"
        if source.get("validationIssues") or source.get("endpointErrorKeys")
        else '<p class="banner success"><strong>The selected backup has a valid strict manifest and no recorded endpoint errors.</strong></p>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(runbook.get('title', 'ZPA Disaster Recovery Runbook'))}</title>
<style>
:root {{ --ink:#172033; --muted:#52637a; --line:#d8e0ea; --paper:#fff; --canvas:#f4f7fb;
  --blue:#1859a9; --green:#087443; --amber:#9a6700; --red:#b42318; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--canvas); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.45; }}
main {{ max-width:1180px; margin:0 auto; padding:32px 24px 80px; }}
h1 {{ margin:0 0 6px; font-size:30px; letter-spacing:-.02em; }}
h2 {{ margin:34px 0 14px; padding-bottom:7px; border-bottom:2px solid var(--ink); font-size:21px; }}
h3 {{ font-size:16px; }} h4 {{ margin:18px 0 6px; font-size:14px; }}
p {{ max-width:90ch; }} .muted {{ color:var(--muted); }}
.banner {{ padding:12px 14px; border-left:4px solid; background:var(--paper); }}
.success {{ color:var(--green); border-color:var(--green); }} .danger {{ color:var(--red); border-color:var(--red); }}
.summary {{ display:grid; grid-template-columns:repeat(5,minmax(110px,1fr)); gap:10px; margin:20px 0; }}
.metric {{ background:var(--paper); border:1px solid var(--line); padding:13px; }}
.metric strong {{ display:block; font-size:24px; }} .metric span {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
table {{ width:100%; border-collapse:collapse; margin:12px 0; background:var(--paper); }}
th,td {{ border:1px solid var(--line); padding:7px 9px; text-align:left; vertical-align:top; font-size:12px; }}
th {{ background:#eef3f8; }}
.item {{ background:var(--paper); border:1px solid var(--line); border-left:5px solid var(--amber); margin:12px 0; padding:16px; break-inside:avoid; }}
.item.status-completed,.item.status-not-applicable {{ border-left-color:var(--green); }}
.item.status-blocked {{ border-left-color:var(--red); }}
.item header {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:flex-start; font-weight:700; }}
.item header label {{ margin-right:auto; font-size:16px; }}
.item input {{ width:17px; height:17px; vertical-align:-3px; }}
.badge {{ display:inline-block; border:1px solid currentColor; padding:2px 7px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; }}
.badge.status {{ color:var(--blue); }} .badge.gap {{ color:var(--red); }}
.sequence {{ color:var(--muted); }} .detail {{ color:var(--muted); }}
.metadata th {{ width:190px; }} ol {{ padding-left:24px; }} li {{ margin:5px 0; }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#101827; color:#edf2f7; padding:11px; font:12px ui-monospace,SFMono-Regular,Menlo,monospace; }}
.evidence {{ border:1px dashed var(--line); padding:10px 12px; margin-top:12px; }}
.evidence dl {{ display:grid; grid-template-columns:100px 1fr; gap:3px 10px; margin:6px 0 0; }}
.evidence dt {{ font-weight:700; }} .evidence dd {{ margin:0; }}
.update {{ margin-bottom:4px; color:var(--muted); font-size:12px; }}
footer {{ margin-top:36px; padding-top:16px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
@media (max-width:760px) {{ .summary {{ grid-template-columns:repeat(2,1fr); }} main {{ padding:20px 12px 60px; }} .metadata th {{ width:auto; }} }}
@media print {{
  body {{ background:#fff; }} main {{ max-width:none; padding:0; }}
  .summary {{ grid-template-columns:repeat(5,1fr); }}
  .item {{ break-inside:avoid; }} pre {{ color:#000; background:#f3f4f6; border:1px solid #bbb; }}
  .update {{ display:none; }} a {{ color:#000; }}
}}
</style>
</head>
<body><main>
<header>
  <h1>{esc(runbook.get('title', 'ZPA Disaster Recovery Runbook'))}</h1>
  <p class="muted">Generated {esc(runbook.get('createdAt', ''))}; updated {esc(runbook.get('updatedAt', ''))}. Sensitive operational record—protect and retain with the recovery evidence package.</p>
</header>
{verification_banner}
{backup_banner}
<section>
  <h2>Executive Checklist Status</h2>
  <div class="summary">
    <div class="metric"><strong>{esc(summary.get('completionPercent', 0))}%</strong><span>Addressed</span></div>
    <div class="metric"><strong>{esc(summary.get('completed', 0))}</strong><span>Completed</span></div>
    <div class="metric"><strong>{esc(summary.get('pending', 0))}</strong><span>Pending</span></div>
    <div class="metric"><strong>{esc(summary.get('blocked', 0))}</strong><span>Blocked</span></div>
    <div class="metric"><strong>{esc(summary.get('notApplicable', 0))}</strong><span>Not applicable</span></div>
  </div>
  <table><tbody>
    <tr><th>Source artifact</th><td>{esc(source.get('artifactPath', ''))}</td></tr>
    <tr><th>Artifact SHA-256</th><td>{esc(source.get('artifactSha256', ''))}</td></tr>
    <tr><th>Backup content SHA-256</th><td>{esc(source.get('contentSha256', ''))}</td></tr>
    <tr><th>Tenant</th><td>{esc(source.get('tenantLabel', ''))} / customer hint {esc(source.get('customerHint', ''))}</td></tr>
    <tr><th>Captured</th><td>{esc(source.get('capturedAt', ''))}</td></tr>
    <tr><th>Captured settings</th><td>{esc(summary.get('settingItems', 0))}</td></tr>
  </tbody></table>
</section>
{_render_coverage(runbook)}
{phases}
<footer>
  <p><strong>Integrity:</strong> plan {esc(integrity.get('planSha256', ''))}; state {esc(integrity.get('stateSha256', ''))}; audit head {esc(integrity.get('auditHeadSha256', '') or 'no checklist events')}.</p>
  <p>This tool is independent and is not affiliated with, endorsed by, sponsored by, certified by, or supported by Zscaler, Inc. It is provided as is without warranty. The checklist covers the selected backup, modeled domains, and known exclusions; it is not proof of complete coverage for future or unmodeled ZPA APIs.</p>
</footer>
</main></body></html>"""


def write_disaster_recovery_report(
    path: Path,
    runbook: dict[str, Any],
    *,
    runbook_path: Path | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_disaster_recovery_report(
            runbook,
            runbook_path=runbook_path,
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        os.chmod(path, 0o600)
    return path


__all__ = [
    "render_disaster_recovery_report",
    "write_disaster_recovery_report",
]
