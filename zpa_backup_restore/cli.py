"""Command-line orchestration for the v2 package."""

from __future__ import annotations

import argparse
import csv
import io
import os
import shlex
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from zpa_backup_restore import __version__
from zpa_backup_restore.api import (
    ApiAuditLogger,
    DEFAULT_LEGACY_ZPA_BASE_URL,
    DEFAULT_ONEAPI_BASE_URL,
    ZscalerClient,
    dump_json,
    env,
    normalize_auth_mode,
    require_env,
)
from zpa_backup_restore.core.backup import backup_tenant, print_run_header
from zpa_backup_restore.core.catalog import COVERAGE_RESOURCES, MIGRATION_ORDER, POLICY_TYPES, RESOURCES
from zpa_backup_restore.core.diff import SPECIAL_DIFF_RESOURCES, diff_action_totals
from zpa_backup_restore.core.integrity import (
    diff_has_changes,
    preflight_restore,
    sha256_text,
    validate_backup,
    validate_diff,
)
from zpa_backup_restore.core.restore import apply_diff
from zpa_backup_restore.core.selection import (
    SELECTABLE_RESOURCE_TYPES,
    canonical_selector,
    compute_restore_diff,
    scope_from_diff,
)
from zpa_backup_restore.errors import CliError
from zpa_backup_restore.reporting.disaster_recovery import (
    write_disaster_recovery_report,
)
from zpa_backup_restore.reporting.html_report import write_report
from zpa_backup_restore.repositories import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_RUN_LEDGER_PATH,
    JsonlRunAuditLedger,
    SQLiteSnapshotCatalog,
)
from zpa_backup_restore.services import (
    AuditService,
    FileExecutionJournal,
    InventoryService,
    SnapshotService,
    build_disaster_recovery_runbook,
    load_disaster_recovery_runbook,
    save_disaster_recovery_runbook,
    update_disaster_recovery_checklist,
    verify_disaster_recovery_runbook,
)
from zpa_backup_restore.services.disaster_recovery import DR_CHECKLIST_STATUSES
from zpa_backup_restore.services.assurance import (
    build_assured_simulation,
    fresh_destination_diff,
    validate_reviewed_simulation,
)
from zpa_backup_restore.services.snapshots import sha256_file
from zpa_backup_restore.security import redact_text
from zpa_backup_restore.storage.backups import (
    DEFAULT_BACKUP_PASSPHRASE_ENV,
    DEFAULT_OPENSSL_BIN,
    encrypted_path,
    load_json_file,
    save_json,
)
BACKUPS_DIR = Path("backups")
LOGS_DIR = Path("logs")
APP_DISPLAY_NAME = "ZPA-Backup and Restore"
LOG_LEVELS = ("normal", "verbose")
OUTPUT_FORMATS = ("table", "json", "csv")


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def profile_client(profile: str, args: argparse.Namespace) -> ZscalerClient:
    prefix = f"ZPA_{profile.upper()}_"
    return ZscalerClient(
        client_id=require_env(f"{prefix}CLIENT_ID"),
        client_secret=require_env(f"{prefix}CLIENT_SECRET"),
        customer_id=require_env(f"{prefix}CUSTOMER_ID"),
        auth_mode=normalize_auth_mode(env(f"{prefix}AUTH_MODE", args.auth_mode)),
        zidentity_base_url=env(f"{prefix}ZIDENTITY_BASE_URL", args.zidentity_base_url),
        oneapi_base_url=env(f"{prefix}ONEAPI_BASE_URL", args.oneapi_base_url),
        legacy_zpa_base_url=env(f"{prefix}ZPA_BASE_URL", args.zpa_base_url),
        audience=args.audience,
        microtenant_id=env(f"{prefix}MICROTENANT_ID", args.microtenant_id),
        audit_logger=getattr(args, "audit_logger", None),
    )


def default_audit_log_path(command: str) -> Path:
    return LOGS_DIR / f"{now_stamp()}-{command}.log"


def configure_audit(args: argparse.Namespace) -> None:
    audit_path = Path(args.audit_log) if args.audit_log else default_audit_log_path(args.command)
    args.audit_log_path = audit_path
    args.audit_logger = ApiAuditLogger(audit_path, progress=not args.no_api_progress)
    args.audit_logger.log_event(
        "run.start",
        command=args.command,
        auth_mode=args.auth_mode,
        log_level=args.log_level,
        policy_types=args.policy_type,
    )
    print(
        f"audit log: {audit_path}",
        file=sys.stderr if getattr(args, "json", False) else sys.stdout,
    )


def _command_name(args: argparse.Namespace) -> str:
    for attribute in (
        "snapshot_command",
        "inventory_command",
        "audit_command",
        "dr_command",
    ):
        child = getattr(args, attribute, None)
        if child:
            return f"{args.command}.{child}"
    return args.command


def configure_run_ledger(args: argparse.Namespace) -> None:
    args.run_id = str(uuid.uuid4())
    args.run_ledger_writer = None
    args.recorded_artifacts = set()
    if args.no_run_ledger or args.command == "audit":
        return
    ledger = JsonlRunAuditLedger(Path(args.run_ledger))
    ledger.append(
        run_id=args.run_id,
        event_type="run.started",
        data={
            "command": _command_name(args),
            "applicationVersion": __version__,
            "httpAuditLog": str(args.audit_log_path),
            "safeguards": {
                "allowDelete": bool(getattr(args, "allow_delete", False)),
                "allowHighImpact": bool(getattr(args, "allow_high_impact", False)),
                "ignorePreflight": bool(getattr(args, "ignore_preflight", False)),
                "allowFailedBackups": bool(getattr(args, "allow_failed_backups", False)),
            },
        },
    )
    args.run_ledger_writer = ledger
    print(f"run: {args.run_id} (ledger: {args.run_ledger})")


def record_run_artifact(args: argparse.Namespace, role: str, path: str | Path) -> None:
    ledger = getattr(args, "run_ledger_writer", None)
    artifact = Path(path)
    if ledger is None or not artifact.is_file():
        return
    resolved = str(artifact.resolve())
    key = (role, resolved)
    if key in args.recorded_artifacts:
        return
    args.recorded_artifacts.add(key)
    ledger.append(
        run_id=args.run_id,
        event_type="artifact.recorded",
        data={
            "role": role,
            "path": resolved,
            "sha256": sha256_file(artifact),
            "bytes": artifact.stat().st_size,
        },
    )


def record_run_event(args: argparse.Namespace, event_type: str, data: dict[str, Any]) -> None:
    ledger = getattr(args, "run_ledger_writer", None)
    if ledger is not None:
        ledger.append(run_id=args.run_id, event_type=event_type, data=data)


def record_declared_inputs(args: argparse.Namespace) -> None:
    for attribute in (
        "source_backup",
        "target_backup",
        "diff",
        "apply_result",
        "simulation",
        "runbook",
    ):
        value = getattr(args, attribute, None)
        if value:
            record_run_artifact(args, f"input.{attribute.replace('_', '-')}", value)
    for value in getattr(args, "backup", []) or []:
        record_run_artifact(args, "input.backup", value)


def finish_run_ledger(args: argparse.Namespace, *, exit_code: int, error: str = "") -> None:
    ledger = getattr(args, "run_ledger_writer", None)
    if ledger is None:
        return
    record_run_artifact(args, "output.http-audit", args.audit_log_path)
    http_hash = sha256_file(args.audit_log_path) if Path(args.audit_log_path).is_file() else ""
    ledger.append(
        run_id=args.run_id,
        event_type="run.finished",
        data={
            "command": _command_name(args),
            "exitCode": exit_code,
            "result": "succeeded" if exit_code == 0 else "failed",
            "error": error,
            "httpAuditLogSha256": http_hash,
        },
    )


def print_restore_header(
    diff: dict[str, Any],
    *,
    dry_run: bool,
    allow_delete: bool,
    allow_high_impact: bool,
) -> None:
    totals = diff_action_totals(diff)
    print(f"restore plan: mode={'DRY-RUN' if dry_run else 'WRITE'}")
    print(
        "restore plan: "
        f"create={totals['create']} update={totals['update']} delete={totals['delete']}"
    )
    print(f"restore safeguards: deletes={'enabled' if allow_delete else 'disabled'}")
    print(f"restore safeguards: high-impact={'enabled' if allow_high_impact else 'disabled'}")


def print_summary(diff: dict[str, Any]) -> None:
    print("Resource                 Create  Update  Delete  Unchanged")
    print("-----------------------  ------  ------  ------  ---------")
    for key in (*MIGRATION_ORDER, *SPECIAL_DIFF_RESOURCES):
        row = diff.get("summary", {}).get(key)
        if not row:
            continue
        print(
            f"{key[:23].ljust(23)}  {str(row['create']).rjust(6)}  "
            f"{str(row['update']).rjust(6)}  {str(row['delete']).rjust(6)}  "
            f"{str(row['unchanged']).rjust(9)}"
        )


def backup_paths(*, encrypt_backups: bool = False) -> tuple[Path, Path, Path]:
    stamp = now_stamp()
    source = BACKUPS_DIR / f"{stamp}-source.json"
    target = BACKUPS_DIR / f"{stamp}-target.json"
    return (
        encrypted_path(source) if encrypt_backups else source,
        encrypted_path(target) if encrypt_backups else target,
        BACKUPS_DIR / f"{stamp}-diff.json",
    )


def backup_tenant_for_args(
    client: ZscalerClient,
    label: str,
    out_path: Path,
    policy_types: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return backup_tenant(
        client,
        label,
        out_path,
        policy_types,
        log_level=args.log_level,
        encrypt_backups=args.encrypt_backups,
        passphrase_env=args.backup_passphrase_env,
        openssl_bin=args.openssl_bin,
    )


def load_json_for_args(path: str | Path, args: argparse.Namespace) -> Any:
    return load_json_file(
        Path(path),
        passphrase_env=args.backup_passphrase_env,
        openssl_bin=args.openssl_bin,
    )


def register_generated_snapshot(backup: dict[str, Any], path: Path, args: argparse.Namespace) -> str:
    """Register a generated backup through the application service boundary."""
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshot = SnapshotService(catalog).register_backup(backup, path)
    print(f"snapshot: {snapshot.snapshot_id[:12]} (catalog: {args.catalog})")
    return snapshot.snapshot_id


def _csv_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fields = list(rows[0])
    for row in rows[1:]:
        fields.extend(key for key in row if key not in fields)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _emit_structured(
    rows: list[dict[str, Any]],
    *,
    output_format: str,
    out: str | None = None,
    output_label: str = "inventory export",
) -> bool:
    """Emit JSON/CSV to stdout or a file; return False for caller-owned table output."""
    if output_format == "table" and not out:
        return False
    actual_format = output_format if output_format != "table" else "json"
    text = dump_json(rows) + "\n" if actual_format == "json" else _csv_text(rows)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"{output_label}: {path}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return True


def _short(value: str, length: int = 12) -> str:
    return value[:length] if value else "-"


def restore_target_backup_path(stamp: str, *, encrypt_backups: bool = False) -> Path:
    path = BACKUPS_DIR / f"{stamp}-restore-target.json"
    return encrypted_path(path) if encrypt_backups else path


def restore_checkpoint_backup_path(
    stamp: str,
    phase: str,
    *,
    encrypt_backups: bool = False,
) -> Path:
    path = BACKUPS_DIR / f"{stamp}-{phase}-restore-target.json"
    return encrypted_path(path) if encrypt_backups else path


def policy_types_for_restore_source(source_backup: dict[str, Any], fallback: list[str]) -> list[str]:
    policy_types = source_backup.get("meta", {}).get("policyTypes")
    if isinstance(policy_types, list):
        clean = [str(policy_type) for policy_type in policy_types if policy_type]
        if clean:
            return clean
    return fallback


def effective_policy_types(policy_types: list[str]) -> list[str]:
    return policy_types or list(POLICY_TYPES)


def restore_diff_for_args(
    source: dict[str, Any],
    target: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return compute_restore_diff(
        source,
        target,
        selectors=getattr(args, "select", ()) or (),
        resource_types=getattr(args, "select_resource", ()) or (),
        include_dependencies=bool(getattr(args, "include_dependencies", False)),
        restore_policy_order=bool(getattr(args, "restore_policy_order", False)),
    )


def print_restore_scope(diff: dict[str, Any]) -> None:
    scope = scope_from_diff(diff)
    if scope is None:
        print("restore scope: complete backup")
        return
    print(
        "restore scope: "
        f"{len(scope.get('resolvedSelectors', []))} selected object(s), "
        f"dependencies={'included' if scope.get('includeDependencies') else 'validate-only'}, "
        f"policy-order={scope.get('policyOrder', 'preserve-target')}"
    )
    for selector in scope.get("resolvedSelectors", []) or []:
        reason = selector.get("reason", "selected")
        print(f"scope {reason}: {selector.get('selector', '')}")


def record_restore_scope(args: argparse.Namespace, diff: dict[str, Any]) -> None:
    scope = scope_from_diff(diff)
    record_run_event(
        args,
        "restore.scope",
        {"mode": "complete"} if scope is None else scope,
    )


def _shell_command(arguments: list[str | Path]) -> str:
    return shlex.join([str(argument) for argument in arguments])


def _backup_crypto_replay_args(
    args: argparse.Namespace,
    *artifact_paths: str | Path,
) -> list[str | Path]:
    encrypted = bool(getattr(args, "encrypt_backups", False))
    encrypted = encrypted or any(str(path).endswith(".enc") for path in artifact_paths)
    if not encrypted:
        return []
    replay: list[str | Path] = []
    if getattr(args, "encrypt_backups", False):
        replay.append("--encrypt-backups")
    replay.extend(
        [
            "--backup-passphrase-env",
            args.backup_passphrase_env,
            "--openssl-bin",
            args.openssl_bin,
        ]
    )
    return replay


def command_backup(args: argparse.Namespace) -> None:
    source_path, target_path, _ = backup_paths(encrypt_backups=args.encrypt_backups)
    if args.tenant in ("source", "both"):
        source = backup_tenant_for_args(
            profile_client("source", args), "source", source_path, args.policy_type, args
        )
        register_generated_snapshot(source, source_path, args)
        record_run_artifact(args, "output.source-backup", source_path)
        print(f"source backup: {source_path}")
    if args.tenant in ("target", "both"):
        target = backup_tenant_for_args(
            profile_client("target", args), "target", target_path, args.policy_type, args
        )
        register_generated_snapshot(target, target_path, args)
        record_run_artifact(args, "output.target-backup", target_path)
        print(f"target backup: {target_path}")


def command_diff(args: argparse.Namespace) -> None:
    source = load_json_for_args(args.source_backup, args)
    target = load_json_for_args(args.target_backup, args)
    if not args.allow_invalid_backup:
        issues = [
            *(f"source backup: {issue}" for issue in validate_backup(source, strict=args.strict_manifest)),
            *(f"target backup: {issue}" for issue in validate_backup(target, strict=args.strict_manifest)),
        ]
        if issues:
            raise CliError("Backup validation failed:\n" + "\n".join(f"- {issue}" for issue in issues))
    diff = restore_diff_for_args(source, target, args)
    record_restore_scope(args, diff)
    print_restore_scope(diff)
    print_summary(diff)
    if args.out:
        save_json(Path(args.out), diff)
        record_run_artifact(args, "output.diff", args.out)
        print(f"diff written: {args.out}")
    if args.report_out:
        write_report(
            Path(args.report_out),
            title=f"{APP_DISPLAY_NAME} Diff Report",
            source_backup=source,
            target_backup=target,
            diff=diff,
        )
        record_run_artifact(args, "output.report", args.report_out)
        print(f"report written: {args.report_out}")


def command_plan(args: argparse.Namespace) -> None:
    source_path, target_path, diff_path = backup_paths(encrypt_backups=args.encrypt_backups)
    report_path = diff_path.with_suffix(".html")
    print_run_header("plan", mode="read-only", policy_types=args.policy_type)
    source = backup_tenant_for_args(profile_client("source", args), "source", source_path, args.policy_type, args)
    target = backup_tenant_for_args(profile_client("target", args), "target", target_path, args.policy_type, args)
    register_generated_snapshot(source, source_path, args)
    register_generated_snapshot(target, target_path, args)
    diff = restore_diff_for_args(source, target, args)
    record_restore_scope(args, diff)
    save_json(diff_path, diff)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} Plan Report",
        source_backup=source,
        target_backup=target,
        diff=diff,
    )
    record_run_artifact(args, "output.source-backup", source_path)
    record_run_artifact(args, "output.target-backup", target_path)
    record_run_artifact(args, "output.diff", diff_path)
    record_run_artifact(args, "output.report", report_path)
    print_summary(diff)
    print_restore_scope(diff)
    print(f"source backup: {source_path}")
    print(f"target backup: {target_path}")
    print(f"diff: {diff_path}")
    print(f"report: {report_path}")


def command_restore_plan(args: argparse.Namespace) -> None:
    source_path = Path(args.source_backup)
    source = load_json_for_args(source_path, args)
    if not args.allow_invalid_backup:
        issues = validate_backup(source, strict=True)
        if issues:
            raise CliError("Source backup validation failed:\n" + "\n".join(f"- {issue}" for issue in issues))
    stamp = now_stamp()
    target_path = restore_target_backup_path(stamp, encrypt_backups=args.encrypt_backups)
    diff_path = BACKUPS_DIR / f"{stamp}-restore-diff.json"
    report_path = diff_path.with_suffix(".html")
    policy_types = policy_types_for_restore_source(source, args.policy_type)
    print_run_header("restore-plan", mode="read-only", policy_types=policy_types)
    target = backup_tenant_for_args(profile_client("target", args), "target", target_path, policy_types, args)
    register_generated_snapshot(target, target_path, args)
    diff = restore_diff_for_args(source, target, args)
    record_restore_scope(args, diff)
    save_json(diff_path, diff)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} Restore Plan Report",
        source_backup=source,
        target_backup=target,
        diff=diff,
    )
    record_run_artifact(args, "output.target-backup", target_path)
    record_run_artifact(args, "output.diff", diff_path)
    record_run_artifact(args, "output.report", report_path)
    print_summary(diff)
    print_restore_scope(diff)
    print(f"source backup: {source_path}")
    print(f"target backup: {target_path}")
    print(f"diff: {diff_path}")
    print(f"report: {report_path}")
    if scope_from_diff(diff) is not None:
        print(
            "next simulation command: "
            + _shell_command(
                [
                    "python3",
                    "-m",
                    "zpa_backup_restore",
                    *_backup_crypto_replay_args(args, source_path, target_path),
                    "simulate",
                    "--source-backup",
                    source_path,
                    "--target-backup",
                    target_path,
                    "--diff",
                    diff_path,
                ]
            )
        )


def command_apply(args: argparse.Namespace) -> None:
    if args.dry_run:
        command_simulate(args)
        return
    if not args.yes:
        raise CliError("Refusing to write without --yes. Run plan/diff first and review the output.")
    source = load_json_for_args(args.source_backup, args)
    reviewed_target = load_json_for_args(args.target_backup, args)
    diff = load_json_for_args(args.diff, args)
    record_restore_scope(args, diff)
    issues = preflight_restore(
        source,
        reviewed_target,
        diff,
        allow_failed_backups=args.allow_failed_backups,
    )
    if issues and not args.ignore_preflight:
        raise CliError("Preflight failed:\n" + "\n".join(f"- {issue}" for issue in issues))
    if not diff_has_changes(diff):
        print("No changes in diff. Nothing to apply.")
        return

    calculated_simulation = build_assured_simulation(
        diff,
        source,
        reviewed_target,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
    )
    if calculated_simulation["hasBlockingIssues"]:
        raise CliError(
            "Restore simulation found "
            f"{calculated_simulation['summary']['blocked']} blocked operation(s). "
            "Run simulate and review its JSON/HTML artifacts before restoring."
        )

    reviewed_simulation = None
    simulation_path = getattr(args, "simulation", None)
    if simulation_path:
        reviewed_simulation = load_json_for_args(simulation_path, args)
        if not isinstance(reviewed_simulation, dict):
            raise CliError("Reviewed simulation root must be a JSON object")
        validate_reviewed_simulation(
            reviewed_simulation,
            source,
            reviewed_target,
            diff,
            allow_delete=args.allow_delete,
            allow_high_impact=args.allow_high_impact,
        )
        print(f"reviewed simulation: verified {simulation_path}")
    elif not getattr(args, "allow_unreviewed_plan", False):
        raise CliError(
            "Live restore requires --simulation with the reviewed simulation JSON. "
            "Run simulate first, or use --allow-unreviewed-plan for an explicit audited compatibility bypass."
        )
    else:
        print("WARNING: reviewed simulation requirement bypassed")
        record_run_event(
            args,
            "restore.assurance-bypassed",
            {"reason": "--allow-unreviewed-plan", "command": args.command},
        )

    print_run_header(args.command, mode="dry-run" if args.dry_run else "write")
    print_restore_header(
        diff,
        dry_run=args.dry_run,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
    )

    target_client = profile_client("target", args)
    stamp = now_stamp()
    policy_types = policy_types_for_restore_source(source, args.policy_type)
    pre_restore_path = restore_checkpoint_backup_path(
        stamp,
        "pre",
        encrypt_backups=args.encrypt_backups,
    )
    fresh_target = backup_tenant_for_args(
        target_client,
        "pre-restore-target",
        pre_restore_path,
        policy_types,
        args,
    )
    register_generated_snapshot(fresh_target, pre_restore_path, args)
    record_run_artifact(args, "output.pre-restore-backup", pre_restore_path)

    if reviewed_simulation is not None:
        execution_diff = fresh_destination_diff(
            reviewed_simulation,
            source,
            fresh_target,
            allow_delete=args.allow_delete,
            allow_high_impact=args.allow_high_impact,
        )
    else:
        execution_diff = compute_restore_diff(
            source,
            fresh_target,
            scope=scope_from_diff(diff),
        )
    fresh_issues = preflight_restore(
        source,
        fresh_target,
        execution_diff,
        allow_failed_backups=args.allow_failed_backups,
    )
    if fresh_issues and not args.ignore_preflight:
        raise CliError(
            "Fresh destination preflight failed:\n"
            + "\n".join(f"- {issue}" for issue in fresh_issues)
        )

    action_label = "restore" if args.command == "restore" else "apply"
    execution_journal_path = BACKUPS_DIR / f"{stamp}-{action_label}-execution-journal.json"
    execution_journal = FileExecutionJournal(
        execution_journal_path,
        run_id=getattr(args, "run_id", str(uuid.uuid4())),
        plan_sha256=calculated_simulation["assurance"]["planSha256"],
        scope=scope_from_diff(execution_diff),
    )
    record_run_artifact(args, "output.execution-journal-started", execution_journal_path)
    result = apply_diff(
        target_client,
        execution_diff,
        source,
        fresh_target,
        dry_run=args.dry_run,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
        journal=execution_journal,
    )
    out_path = BACKUPS_DIR / f"{stamp}-{action_label}-result.json"
    report_path = out_path.with_suffix(".html")
    save_json(out_path, result)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} {action_label.title()} Report",
        source_backup=source,
        target_backup=fresh_target,
        diff=execution_diff,
        apply_result=result,
    )
    record_run_artifact(args, f"output.{action_label}-result", out_path)
    record_run_artifact(args, "output.report", report_path)
    record_run_artifact(args, "output.execution-journal-completed", execution_journal_path)

    post_restore_path = restore_checkpoint_backup_path(
        stamp,
        "post",
        encrypt_backups=args.encrypt_backups,
    )
    post_target = backup_tenant_for_args(
        target_client,
        "post-restore-target",
        post_restore_path,
        policy_types,
        args,
    )
    register_generated_snapshot(post_target, post_restore_path, args)
    record_run_artifact(args, "output.post-restore-backup", post_restore_path)
    residual_diff = compute_restore_diff(
        source,
        post_target,
        scope=scope_from_diff(execution_diff),
    )
    residual_path = BACKUPS_DIR / f"{stamp}-{action_label}-residual-diff.json"
    residual_report_path = residual_path.with_suffix(".html")
    save_json(residual_path, residual_diff)
    write_report(
        residual_report_path,
        title=f"{APP_DISPLAY_NAME} Post-{action_label.title()} Verification",
        source_backup=source,
        target_backup=post_target,
        diff=residual_diff,
        apply_result=result,
    )
    record_run_artifact(args, "output.residual-diff", residual_path)
    record_run_artifact(args, "output.residual-report", residual_report_path)
    print(f"{action_label} result: {out_path}")
    print(f"report: {report_path}")
    print(f"execution journal: {execution_journal_path}")
    print(f"pre-restore backup: {pre_restore_path}")
    print(f"post-restore backup: {post_restore_path}")
    print(f"residual diff: {residual_path}")
    print(f"residual report: {residual_report_path}")
    if diff_has_changes(residual_diff):
        totals = diff_action_totals(residual_diff)
        raise CliError(
            "Post-restore verification found residual differences: "
            f"create={totals['create']} update={totals['update']} delete={totals['delete']}. "
            "Review the residual report; this run is not marked successful."
        )


def command_restore(args: argparse.Namespace) -> None:
    command_apply(args)


def _print_simulation(simulation: dict[str, Any]) -> None:
    for operation in simulation["operations"]:
        status = {
            "planned": "DRY-RUN",
            "skipped": "SKIP",
            "blocked": "ERROR",
        }[operation["status"]]
        request = operation.get("request") or {}
        detail = operation.get("reason") or (
            f"{request.get('method', '')} {request.get('path', '')} "
            f"payload={operation.get('payloadStatus', 'none')}"
        ).strip()
        print(
            f"{operation['action']:<7} {operation['resource']:<22} "
            f"{status:<7} {operation['name']} {detail}".rstrip()
        )

    summary = simulation["summary"]
    print(
        "simulation summary: "
        f"planned={summary['planned']} skipped={summary['skipped']} "
        f"blocked={summary['blocked']} deferred={summary['deferredOperations']} "
        f"unresolved={summary['unresolvedReferences']}"
    )
    for reason, count in simulation.get("skipReasons", {}).items():
        print(f"simulation skipped: {reason}={count}")
    for operation in simulation["operations"]:
        if operation["status"] == "blocked":
            print(
                f"simulation blocker: #{operation['sequence']} "
                f"{operation['action']} {operation['resource']} {operation['name']}: "
                f"{operation['reason']}"
            )


def command_simulate(args: argparse.Namespace) -> None:
    source = load_json_for_args(args.source_backup, args)
    target = load_json_for_args(args.target_backup, args)
    diff = load_json_for_args(args.diff, args)
    record_restore_scope(args, diff)
    issues = preflight_restore(
        source,
        target,
        diff,
        allow_failed_backups=args.allow_failed_backups,
    )
    if issues and not args.ignore_preflight:
        raise CliError("Preflight failed:\n" + "\n".join(f"- {issue}" for issue in issues))

    print_run_header("simulate", mode="offline")
    print_restore_scope(diff)
    print_restore_header(
        diff,
        dry_run=True,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
    )
    simulation = build_assured_simulation(
        diff,
        source,
        target,
        allow_delete=args.allow_delete,
        allow_high_impact=args.allow_high_impact,
    )
    _print_simulation(simulation)

    out_path = Path(getattr(args, "out", "") or BACKUPS_DIR / f"{now_stamp()}-simulation.json")
    report_path = Path(
        getattr(args, "report_out", "") or out_path.with_suffix(".html")
    )
    save_json(out_path, simulation)
    write_report(
        report_path,
        title=f"{APP_DISPLAY_NAME} Restore Simulation",
        source_backup=source,
        target_backup=target,
        diff=diff,
        apply_result=simulation,
    )
    record_run_artifact(args, "output.simulation", out_path)
    record_run_artifact(args, "output.report", report_path)
    print(f"simulation: {out_path}")
    print(f"report: {report_path}")
    if simulation["hasBlockingIssues"]:
        raise CliError(
            "Simulation found "
            f"{simulation['summary']['blocked']} blocked operation(s); review the simulation artifact."
        )
    restore_arguments: list[str | Path] = [
        "python3",
        "-m",
        "zpa_backup_restore",
        *_backup_crypto_replay_args(
            args,
            args.source_backup,
            args.target_backup,
        ),
        "restore",
        "--source-backup",
        args.source_backup,
        "--target-backup",
        args.target_backup,
        "--diff",
        args.diff,
        "--simulation",
        out_path,
        "--yes",
    ]
    if args.allow_delete:
        restore_arguments.append("--allow-delete")
    if args.allow_high_impact:
        restore_arguments.append("--allow-high-impact")
    if args.allow_failed_backups:
        restore_arguments.append("--allow-failed-backups")
    if args.ignore_preflight:
        restore_arguments.append("--ignore-preflight")
    print("reviewed restore command: " + _shell_command(restore_arguments))


def command_report(args: argparse.Namespace) -> None:
    write_report(
        Path(args.out),
        title=args.title,
        source_backup=load_json_for_args(args.source_backup, args) if args.source_backup else None,
        target_backup=load_json_for_args(args.target_backup, args) if args.target_backup else None,
        diff=load_json_for_args(args.diff, args) if args.diff else None,
        apply_result=load_json_for_args(args.apply_result, args) if args.apply_result else None,
        include_coverage=not args.no_coverage,
    )
    record_run_artifact(args, "output.report", args.out)
    print(f"report written: {args.out}")


def _default_dr_runbook_path() -> Path:
    return BACKUPS_DIR / f"{now_stamp()}-dr-runbook.json"


def _default_dr_report_path(runbook_path: Path) -> Path:
    return runbook_path.with_suffix(".html")


def _dr_command_prefix(
    args: argparse.Namespace,
    source_backup: str | Path,
) -> list[str | Path]:
    return [
        "python3",
        "-m",
        "zpa_backup_restore",
        *_backup_crypto_replay_args(args, source_backup),
    ]


def _print_dr_summary(runbook: dict[str, Any]) -> None:
    summary = runbook.get("summary", {}) or {}
    print(
        "dr summary: "
        f"settings={summary.get('settingItems', 0)} "
        f"completed={summary.get('completed', 0)} "
        f"pending={summary.get('pending', 0)} "
        f"blocked={summary.get('blocked', 0)} "
        f"not-applicable={summary.get('notApplicable', 0)} "
        f"addressed={summary.get('completionPercent', 0)}%"
    )


def command_dr_generate(args: argparse.Namespace) -> None:
    source_path = Path(args.source_backup)
    backup = load_json_for_args(source_path, args)
    runbook_path = Path(args.out) if args.out else _default_dr_runbook_path()
    report_path = (
        Path(args.report_out)
        if args.report_out
        else _default_dr_report_path(runbook_path)
    )
    runbook = build_disaster_recovery_runbook(
        backup,
        source_path,
        command_prefix=_dr_command_prefix(args, source_path),
        title=args.title,
    )
    save_disaster_recovery_runbook(runbook_path, runbook)
    write_disaster_recovery_report(
        report_path,
        runbook,
        runbook_path=runbook_path.resolve(),
    )
    record_run_artifact(args, "output.dr-runbook", runbook_path)
    record_run_artifact(args, "output.dr-checklist", report_path)
    record_run_event(
        args,
        "dr.runbook.generated",
        {
            "planSha256": runbook["integrity"]["planSha256"],
            "itemCount": runbook["summary"]["total"],
            "settingCount": runbook["summary"]["settingItems"],
            "blockedCount": runbook["summary"]["blocked"],
        },
    )
    _print_dr_summary(runbook)
    print(f"dr runbook: {runbook_path}")
    print(f"dr checklist: {report_path}")


def _verified_dr_runbook(
    args: argparse.Namespace,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    path = Path(args.runbook)
    runbook = load_disaster_recovery_runbook(path)
    verification = verify_disaster_recovery_runbook(
        runbook,
        check_source=not getattr(args, "allow_missing_source", False),
    )
    if not verification["valid"]:
        raise CliError(
            "DR runbook verification failed:\n"
            + "\n".join(f"- {error}" for error in verification["errors"])
        )
    return path, runbook, verification


def command_dr_status(args: argparse.Namespace) -> None:
    _path, runbook, verification = _verified_dr_runbook(args)
    selected_statuses = set(args.status or DR_CHECKLIST_STATUSES)
    items = [
        item
        for item in runbook.get("items", []) or []
        if item.get("status") in selected_statuses
    ]
    rows = [
        {
            "sequence": item.get("sequence"),
            "id": item.get("id"),
            "status": item.get("status"),
            "phase": item.get("phase"),
            "capability": item.get("capability"),
            "resource_type": item.get("resourceType"),
            "name": item.get("name"),
            "operator": item.get("operator"),
            "evidence": item.get("evidence"),
        }
        for item in items
    ]
    if args.format in {"json", "csv"} or args.out:
        if args.format == "csv":
            _emit_structured(
                rows,
                output_format="csv",
                out=args.out,
                output_label="dr status",
            )
        else:
            payload = {
                "verification": verification,
                "summary": runbook.get("summary", {}),
                "items": rows,
            }
            text = dump_json(payload) + "\n"
            if args.out:
                path = Path(args.out)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                record_run_artifact(args, "output.dr-status", path)
                print(f"dr status: {path}")
            else:
                print(text, end="")
        return
    _print_dr_summary(runbook)
    print(" #    Status          Capability        Resource type             Name / checklist item")
    print("----  --------------  ----------------  ------------------------  ----------------------------------------")
    for row in rows:
        print(
            f"{str(row['sequence']).rjust(4)}  "
            f"{str(row['status'])[:14].ljust(14)}  "
            f"{str(row['capability'])[:16].ljust(16)}  "
            f"{str(row['resource_type'])[:24].ljust(24)}  "
            f"{str(row['name'])[:40]}"
        )
    if not rows:
        print("(no checklist items matched)")


def command_dr_check(args: argparse.Namespace) -> None:
    runbook_path = Path(args.runbook)
    runbook = load_disaster_recovery_runbook(runbook_path)
    item = update_disaster_recovery_checklist(
        runbook,
        item_identifier=args.item,
        status=args.status,
        operator=args.actor,
        evidence=args.evidence,
        note=args.note,
    )
    save_disaster_recovery_runbook(runbook_path, runbook)
    report_path = (
        Path(args.report_out)
        if args.report_out
        else _default_dr_report_path(runbook_path)
    )
    write_disaster_recovery_report(
        report_path,
        runbook,
        runbook_path=runbook_path.resolve(),
    )
    record_run_event(
        args,
        "dr.checklist.updated",
        {
            "itemId": item["id"],
            "fromStatus": runbook["auditTrail"][-1]["fromStatus"],
            "toStatus": item["status"],
            "actor": item["operator"],
            "evidenceSha256": sha256_text(item["evidence"])
            if item["evidence"]
            else "",
            "planSha256": runbook["integrity"]["planSha256"],
            "stateSha256": runbook["integrity"]["stateSha256"],
        },
    )
    record_run_artifact(args, "output.dr-runbook", runbook_path)
    record_run_artifact(args, "output.dr-checklist", report_path)
    print(
        f"dr checklist updated: {item['id']} "
        f"{runbook['auditTrail'][-1]['fromStatus']} -> {item['status']}"
    )
    _print_dr_summary(runbook)
    print(f"dr runbook: {runbook_path}")
    print(f"dr checklist: {report_path}")


def command_dr_report(args: argparse.Namespace) -> None:
    runbook_path, runbook, _verification = _verified_dr_runbook(args)
    report_path = Path(args.out)
    write_disaster_recovery_report(
        report_path,
        runbook,
        runbook_path=runbook_path.resolve(),
    )
    record_run_artifact(args, "output.dr-checklist", report_path)
    print(f"dr checklist: {report_path}")


def command_dr_verify(args: argparse.Namespace) -> None:
    path = Path(args.runbook)
    runbook = load_disaster_recovery_runbook(path)
    verification = verify_disaster_recovery_runbook(
        runbook,
        check_source=not args.allow_missing_source,
    )
    print(dump_json(verification))
    if not verification["valid"]:
        raise CliError("DR runbook verification failed")


def command_coverage(args: argparse.Namespace) -> None:
    rows = [
        {
            "resource": key,
            "mode": meta.get("mode", "clone" if meta.get("writable") else "reference"),
            "sensitivity": meta.get("sensitivity", "normal"),
            "actions": meta.get("actions", []),
            "operation_source": meta.get("operation_source", "compatibility"),
            "endpoint": meta.get("path", ""),
            "depends_on": ", ".join(meta.get("depends_on", [])),
            "notes": meta.get("notes", ""),
            "operations": meta.get("operations", []),
        }
        for key, meta in COVERAGE_RESOURCES.items()
    ]
    if args.json:
        print(dump_json(rows))
        return
    operation_count = sum(len(row["operations"]) for row in rows)
    print(f"Coverage: {len(rows)} domains, {operation_count} explicit API operations")
    print("Resource                  Mode       Sensitivity  Source         Operations")
    print("------------------------  ---------  -----------  -------------  ------------------------------")
    for row in rows:
        actions = ",".join(
            operation["key"]
            if operation.get("support", "enabled") == "enabled"
            else f"{operation['key']}[{operation['support']}]"
            for operation in row["operations"]
        )
        print(
            f"{row['resource'][:24].ljust(24)}  {row['mode'][:9].ljust(9)}  "
            f"{row['sensitivity'][:11].ljust(11)}  "
            f"{row['operation_source'][:13].ljust(13)}  {actions}"
        )


def command_validate(args: argparse.Namespace) -> None:
    if not args.backup and not args.diff:
        raise CliError("Nothing to validate. Pass --backup and/or --diff.")
    failed = False
    for backup_path in args.backup:
        issues = validate_backup(load_json_for_args(backup_path, args), strict=args.strict_manifest)
        print(f"{backup_path}: {'invalid' if issues else 'valid'}")
        for issue in issues:
            print(f"  - {issue}")
        failed = failed or bool(issues)
    for diff_path in args.diff:
        issues = validate_diff(load_json_for_args(diff_path, args))
        print(f"{diff_path}: {'invalid' if issues else 'valid'}")
        for issue in issues:
            print(f"  - {issue}")
        failed = failed or bool(issues)
    if failed:
        raise CliError("Validation failed")


def command_preflight(args: argparse.Namespace) -> None:
    issues = preflight_restore(
        load_json_for_args(args.source_backup, args),
        load_json_for_args(args.target_backup, args),
        load_json_for_args(args.diff, args),
        allow_failed_backups=args.allow_failed_backups,
    )
    if issues:
        print("Preflight failed:")
        for issue in issues:
            print(f"- {issue}")
        raise CliError("Preflight failed")
    diff = load_json_for_args(args.diff, args)
    print(f"Preflight passed. Diff contains {'changes' if diff_has_changes(diff) else 'no changes'}.")


def command_snapshot_list(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshots = catalog.list_snapshots(limit=args.limit)
    rows = [snapshot.as_dict() for snapshot in snapshots]
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    print("Snapshot      Captured at                Tenant       Items  Errors  Verified  Artifact")
    print("------------  -------------------------  -----------  -----  ------  --------  --------")
    for snapshot in snapshots:
        tenant = f"{snapshot.tenant_label}:{snapshot.customer_hint or '-'}"
        print(
            f"{_short(snapshot.snapshot_id):12}  {snapshot.captured_at[:25]:25}  "
            f"{tenant[:11]:11}  {snapshot.resource_count:5}  {snapshot.error_count:6}  "
            f"{str(snapshot.verified):8}  {snapshot.artifact_path}"
        )
    if not snapshots:
        print("(catalog is empty)")


def command_snapshot_import(args: argparse.Namespace) -> None:
    path = Path(args.path)
    record_run_artifact(args, "input.backup", path)
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshot = SnapshotService(catalog).import_backup(
            path,
            lambda artifact: load_json_for_args(artifact, args),
        )
    print(dump_json(snapshot.as_dict()))


def command_snapshot_show(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        service = SnapshotService(catalog)
        snapshot = service.resolve_snapshot(args.snapshot)
        resources = catalog.list_resources(snapshot_id=snapshot.snapshot_id, limit=1_000_000)
    resource_types = dict(sorted(Counter(item.resource_type for item in resources).items()))
    payload = {**snapshot.as_dict(), "resource_types": resource_types}
    print(dump_json(payload))


def command_snapshot_verify(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshot = SnapshotService(catalog).verify_snapshot(
            args.snapshot,
            lambda artifact: load_json_for_args(artifact, args),
        )
    print(f"verified snapshot {_short(snapshot.snapshot_id)}: {snapshot.artifact_path}")


def _inventory_rows(
    args: argparse.Namespace,
    *,
    search: str | None,
) -> tuple[Any, list[Any], dict[str, str]]:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshot, resources = InventoryService(catalog).list_resources(
            snapshot_identifier=args.snapshot,
            resource_type=args.resource_type,
            search=search,
            limit=args.limit,
        )
        if snapshot:
            artifacts = {snapshot.snapshot_id: snapshot.artifact_path}
        else:
            artifacts = {
                item.snapshot_id: item.artifact_path
                for item in catalog.list_snapshots(limit=100_000)
            }
    return snapshot, resources, artifacts


def _restore_plan_command(resource: Any, artifact_path: str | None) -> str:
    if (
        not resource.writable
        or resource.resource_type not in SELECTABLE_RESOURCE_TYPES
        or "#duplicate-" in resource.stable_key
        or not artifact_path
    ):
        return ""
    selector = canonical_selector(resource.resource_type, resource.stable_key)
    return _shell_command(
        [
            "python3",
            "-m",
            "zpa_backup_restore",
            "restore-plan",
            "--source-backup",
            artifact_path,
            "--select",
            selector,
        ]
    )


def _inventory_record(resource: Any, artifact_path: str | None) -> dict[str, Any]:
    selector = (
        canonical_selector(resource.resource_type, resource.stable_key)
        if (
            resource.writable
            and resource.resource_type in SELECTABLE_RESOURCE_TYPES
            and "#duplicate-" not in resource.stable_key
        )
        else ""
    )
    return {
        **resource.as_dict(),
        "restore_selector": selector,
        "restore_plan_command": _restore_plan_command(resource, artifact_path),
    }


def _print_inventory(
    resources: list[Any],
    artifacts: dict[str, str],
    *,
    restore_commands: bool,
) -> None:
    print(
        "Snapshot      Resource type             Name                         "
        "Writable  Impact  Restore selector"
    )
    print(
        "------------  ------------------------  ---------------------------  "
        "--------  ------  ----------------------------------------"
    )
    for resource in resources:
        selector = (
            canonical_selector(resource.resource_type, resource.stable_key)
            if (
                resource.writable
                and resource.resource_type in SELECTABLE_RESOURCE_TYPES
                and "#duplicate-" not in resource.stable_key
            )
            else "-"
        )
        print(
            f"{_short(resource.snapshot_id):12}  {resource.resource_type[:24]:24}  "
            f"{resource.display_name[:27]:27}  {str(resource.writable):8}  "
            f"{'high' if resource.high_impact else 'normal':6}  {selector}"
        )
    if not resources:
        print("(no inventory resources matched)")
    if restore_commands:
        commands = [
            (
                resource.display_name,
                _restore_plan_command(resource, artifacts.get(resource.snapshot_id)),
            )
            for resource in resources
        ]
        commands = [(name, command) for name, command in commands if command]
        if commands:
            print()
            print("Selective restore-plan commands:")
            for name, command in commands:
                print(f"{name}: {command}")
        else:
            print()
            print("(no writable resources matched)")


def command_inventory_list(args: argparse.Namespace) -> None:
    snapshot, resources, artifacts = _inventory_rows(args, search=args.search)
    rows = [
        _inventory_record(resource, artifacts.get(resource.snapshot_id))
        for resource in resources
    ]
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    if snapshot:
        print(f"snapshot: {_short(snapshot.snapshot_id)} {snapshot.captured_at} {snapshot.tenant_label}")
    else:
        print("snapshot: all")
    _print_inventory(
        resources,
        artifacts,
        restore_commands=args.restore_commands,
    )


def command_inventory_search(args: argparse.Namespace) -> None:
    _snapshot, resources, artifacts = _inventory_rows(args, search=args.query)
    rows = [
        _inventory_record(resource, artifacts.get(resource.snapshot_id))
        for resource in resources
    ]
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    _print_inventory(
        resources,
        artifacts,
        restore_commands=args.restore_commands,
    )


def command_inventory_history(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        history = InventoryService(catalog).history(
            resource_type=args.resource_type,
            stable_key=args.stable_key,
            limit=args.limit,
        )
    rows = []
    for index, (snapshot, resource) in enumerate(history):
        older_hash = history[index + 1][1].config_sha256 if index + 1 < len(history) else None
        rows.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at,
                "tenant_label": snapshot.tenant_label,
                "display_name": resource.display_name,
                "config_sha256": resource.config_sha256,
                "changed_since_previous": older_hash is not None and older_hash != resource.config_sha256,
            }
        )
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    print("Snapshot      Captured at                Name                         Changed  Config hash")
    print("------------  -------------------------  ---------------------------  -------  -----------")
    for row in rows:
        print(
            f"{_short(row['snapshot_id']):12}  {row['captured_at'][:25]:25}  "
            f"{row['display_name'][:27]:27}  {str(row['changed_since_previous']):7}  "
            f"{_short(row['config_sha256'])}"
        )
    if not rows:
        print("(no history found; stable keys are normalized and case-insensitive)")


def command_inventory_references(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        snapshot, references = InventoryService(catalog).references(
            snapshot_identifier=args.snapshot,
            resource_type=args.resource_type,
            stable_key=args.stable_key,
            direction=args.direction,
            limit=args.limit,
        )
    rows = [reference.as_dict() for reference in references]
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    print(f"snapshot: {_short(snapshot.snapshot_id)} direction={args.direction}")
    print("From                                  Field path                   Target")
    print("------------------------------------  ---------------------------  ------------------------------------")
    for reference in references:
        source = f"{reference.from_resource_type}/{reference.from_stable_key}"
        target = f"{reference.target_resource_type}/{reference.target_stable_key}"
        print(f"{source[:36]:36}  {reference.field_path[:27]:27}  {target[:36]}")
    if not references:
        print("(no references matched)")


def command_inventory_drift(args: argparse.Namespace) -> None:
    with SQLiteSnapshotCatalog(Path(args.catalog)) as catalog:
        drift = InventoryService(catalog).drift(args.from_snapshot, args.to_snapshot)
    payload = drift.as_dict(include_unchanged=args.include_unchanged)
    rows = payload["entries"]
    if args.format in {"json", "csv"} or args.out:
        if args.format == "csv":
            _emit_structured(rows, output_format="csv", out=args.out)
        else:
            text = dump_json(payload) + "\n"
            if args.out:
                path = Path(args.out)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                print(f"inventory export: {path}")
            else:
                print(text, end="")
        return
    summary = drift.summary
    print(
        f"drift: {_short(drift.from_snapshot_id)} -> {_short(drift.to_snapshot_id)} "
        f"same-tenant={drift.same_tenant} added={summary['added']} removed={summary['removed']} "
        f"changed={summary['changed']} unchanged={summary['unchanged']}"
    )
    print("Status     Resource type             Name                         Stable key")
    print("---------  ------------------------  ---------------------------  ---------------------------")
    for entry in drift.entries:
        if entry.status == "unchanged" and not args.include_unchanged:
            continue
        print(
            f"{entry.status:9}  {entry.resource_type[:24]:24}  "
            f"{entry.display_name[:27]:27}  {entry.stable_key[:27]}"
        )


def _audit_service(args: argparse.Namespace) -> AuditService:
    return AuditService(JsonlRunAuditLedger(Path(args.run_ledger)))


def _print_audit_runs(runs: list[dict[str, Any]]) -> None:
    print("Run           Started at            Command                 Status     Artifacts  Error")
    print("------------  --------------------  ----------------------  ---------  ---------  -----")
    for run in runs:
        print(
            f"{_short(run['runId']):12}  {run['startedAt'][:20]:20}  "
            f"{run['command'][:22]:22}  {run['status']:9}  {run['artifactCount']:9}  "
            f"{run['error'][:50]}"
        )
    if not runs:
        print("(no runs matched)")


def command_audit_list(args: argparse.Namespace) -> None:
    runs = _audit_service(args).list_runs(limit=args.limit)
    if _emit_structured(runs, output_format=args.format, out=args.out):
        return
    _print_audit_runs(runs)


def command_audit_failures(args: argparse.Namespace) -> None:
    runs = _audit_service(args).list_runs(failures_only=True, limit=args.limit)
    if _emit_structured(runs, output_format=args.format, out=args.out):
        return
    _print_audit_runs(runs)


def command_audit_summary(args: argparse.Namespace) -> None:
    rows = _audit_service(args).command_summary()
    if _emit_structured(rows, output_format=args.format, out=args.out):
        return
    print("Command                   Total  Succeeded  Failed  Running")
    print("------------------------  -----  ---------  ------  -------")
    for row in rows:
        print(
            f"{row['command'][:24]:24}  {row['total']:5}  {row['succeeded']:9}  "
            f"{row['failed']:6}  {row['running']:7}"
        )
    if not rows:
        print("(ledger is empty)")


def command_audit_show(args: argparse.Namespace) -> None:
    print(dump_json(_audit_service(args).run_detail(args.run)))


def command_audit_verify(args: argparse.Namespace) -> None:
    verification = JsonlRunAuditLedger(Path(args.run_ledger)).verify()
    print(dump_json(verification.as_dict()))
    if not verification.valid:
        raise CliError("Run audit ledger verification failed")


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=OUTPUT_FORMATS, default="table")
    parser.add_argument("--out", help="Write JSON or CSV instead of printing a table.")


def _add_restore_set_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-backup", required=True)
    parser.add_argument("--target-backup", required=True)
    parser.add_argument("--diff", required=True)


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--select",
        action="append",
        default=[],
        metavar="RESOURCE/STABLE_KEY",
        help=(
            "Restore one desired object by stable identity; repeat as needed. "
            "Policy rules also accept policy_rules/POLICY_TYPE/Rule Name."
        ),
    )
    parser.add_argument(
        "--select-resource",
        action="append",
        choices=SELECTABLE_RESOURCE_TYPES,
        default=[],
        help="Restore all differences for one writable resource type; repeat as needed.",
    )
    parser.add_argument(
        "--include-dependencies",
        action="store_true",
        help="Recursively include referenced writable dependency objects in the scope.",
    )
    parser.add_argument(
        "--restore-policy-order",
        action="store_true",
        help="Also restore bulk policy order for selected policy types.",
    )


def _add_safeguard_arguments(parser: argparse.ArgumentParser, *, noun: str) -> None:
    parser.add_argument("--allow-delete", action="store_true", help="Allow deletes. By default deletes are skipped.")
    parser.add_argument("--allow-high-impact", action="store_true", help="Allow writes to high-impact resources such as microtenants.")
    parser.add_argument("--allow-failed-backups", action="store_true", help=f"Allow {noun} when backup files contain endpoint errors.")
    parser.add_argument("--ignore-preflight", action="store_true", help="Bypass restore preflight validation.")


def _add_restore_arguments(parser: argparse.ArgumentParser, *, noun: str) -> None:
    _add_restore_set_arguments(parser)
    parser.add_argument(
        "--simulation",
        help="Reviewed simulation JSON; required for live writes by default.",
    )
    parser.add_argument(
        "--allow-unreviewed-plan",
        action="store_true",
        help="Explicit audited compatibility bypass for the reviewed simulation requirement.",
    )
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility alias for the offline simulate command.")
    _add_safeguard_arguments(parser, noun=noun)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZPA tenant backup/diff/restore tool.")
    parser.add_argument("--auth-mode", choices=("legacy", "oneapi"), default=env("ZSCALER_AUTH_MODE", "legacy"))
    parser.add_argument("--zpa-base-url", default=env("ZSCALER_ZPA_BASE_URL", DEFAULT_LEGACY_ZPA_BASE_URL))
    parser.add_argument("--oneapi-base-url", default=env("ZSCALER_ONEAPI_BASE_URL", DEFAULT_ONEAPI_BASE_URL))
    parser.add_argument("--zidentity-base-url", default=env("ZSCALER_ZIDENTITY_BASE_URL"))
    parser.add_argument("--audience", default="https://api.zscaler.com")
    parser.add_argument("--microtenant-id")
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="normal", help="Logging detail. Default: normal.")
    parser.add_argument("--audit-log", default=env("ZPA_AUDIT_LOG"), help="HTTP audit log path. Default: logs/<timestamp>-<command>.log.")
    parser.add_argument(
        "--catalog",
        default=env("ZPA_CATALOG_PATH", str(DEFAULT_CATALOG_PATH)),
        help=f"Managed snapshot catalog. Default: {DEFAULT_CATALOG_PATH}.",
    )
    parser.add_argument(
        "--run-ledger",
        default=env("ZPA_RUN_LEDGER", str(DEFAULT_RUN_LEDGER_PATH)),
        help=f"Tamper-evident run ledger. Default: {DEFAULT_RUN_LEDGER_PATH}.",
    )
    parser.add_argument("--no-run-ledger", action="store_true", help="Disable run-level audit events for this command.")
    parser.add_argument("--no-api-progress", action="store_true", help="Hide per-request progress; audit logging continues.")
    parser.add_argument("--encrypt-backups", action="store_true", help="Write OpenSSL-encrypted .json.enc backups.")
    parser.add_argument(
        "--backup-passphrase-env",
        default=env("ZPA_BACKUP_PASSPHRASE_ENV", DEFAULT_BACKUP_PASSPHRASE_ENV),
        help=f"Environment variable containing the backup passphrase. Default: {DEFAULT_BACKUP_PASSPHRASE_ENV}.",
    )
    parser.add_argument("--openssl-bin", default=env("ZPA_OPENSSL_BIN", DEFAULT_OPENSSL_BIN), help="OpenSSL executable. Default: openssl.")
    parser.add_argument("--policy-type", action="append", default=[], help="Policy type to include; repeat as needed. Default: all.")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Back up source, target, or both tenants.")
    backup.add_argument("tenant", choices=("source", "target", "both"), nargs="?", default="both")
    backup.set_defaults(func=command_backup)

    diff = sub.add_parser("diff", help="Compare two existing backup files.")
    diff.add_argument("--source-backup", required=True)
    diff.add_argument("--target-backup", required=True)
    diff.add_argument("--out")
    diff.add_argument("--report-out")
    diff.add_argument("--strict-manifest", action="store_true")
    diff.add_argument("--allow-invalid-backup", action="store_true")
    _add_selection_arguments(diff)
    diff.set_defaults(func=command_diff)

    plan = sub.add_parser("plan", help="Back up both tenants and produce a read-only diff.")
    _add_selection_arguments(plan)
    plan.set_defaults(func=command_plan)

    restore_plan = sub.add_parser("restore-plan", help="Compare an existing desired backup with a fresh target backup.")
    restore_plan.add_argument("--source-backup", required=True)
    restore_plan.add_argument("--allow-invalid-backup", action="store_true")
    _add_selection_arguments(restore_plan)
    restore_plan.set_defaults(func=command_restore_plan)

    apply_parser = sub.add_parser("apply", help="Automation alias for a reviewed restore.")
    _add_restore_arguments(apply_parser, noun="apply")
    apply_parser.set_defaults(func=command_apply)

    restore = sub.add_parser("restore", help="Restore a reviewed backup into the target tenant.")
    _add_restore_arguments(restore, noun="restore")
    restore.set_defaults(func=command_restore)

    simulate = sub.add_parser(
        "simulate",
        help="Build an offline ordered restore simulation with sanitized request payloads.",
    )
    _add_restore_set_arguments(simulate)
    _add_safeguard_arguments(simulate, noun="simulation")
    simulate.add_argument("--out", help="Simulation JSON path. Default: backups/<timestamp>-simulation.json.")
    simulate.add_argument("--report-out", help="Simulation HTML path. Default: next to the JSON artifact.")
    simulate.set_defaults(func=command_simulate, dry_run=True, yes=False)

    report = sub.add_parser("report", help="Generate an HTML report from artifacts.")
    report.add_argument("--source-backup")
    report.add_argument("--target-backup")
    report.add_argument("--diff")
    report.add_argument("--apply-result")
    report.add_argument("--out", required=True)
    report.add_argument("--title", default=f"{APP_DISPLAY_NAME} Report")
    report.add_argument("--no-coverage", action="store_true")
    report.set_defaults(func=command_report)

    coverage = sub.add_parser("coverage", help="Show resource coverage.")
    coverage.add_argument("--json", action="store_true")
    coverage.set_defaults(func=command_coverage)

    validate = sub.add_parser("validate", help="Validate backup and diff files.")
    validate.add_argument("--backup", action="append", default=[])
    validate.add_argument("--diff", action="append", default=[])
    validate.add_argument("--strict-manifest", action="store_true")
    validate.set_defaults(func=command_validate)

    preflight = sub.add_parser("preflight", help="Validate a restore set before writing.")
    preflight.add_argument("--source-backup", required=True)
    preflight.add_argument("--target-backup", required=True)
    preflight.add_argument("--diff", required=True)
    preflight.add_argument("--allow-failed-backups", action="store_true")
    preflight.set_defaults(func=command_preflight)

    dr = sub.add_parser(
        "dr",
        help="Generate and audit a setting-by-setting disaster-recovery runbook.",
    )
    dr_sub = dr.add_subparsers(dest="dr_command", required=True)

    dr_generate = dr_sub.add_parser(
        "generate",
        help="Build credential-free JSON and HTML recovery checklists from a backup.",
    )
    dr_generate.add_argument("--source-backup", required=True)
    dr_generate.add_argument(
        "--out",
        help="Runbook JSON path. Default: backups/<timestamp>-dr-runbook.json.",
    )
    dr_generate.add_argument(
        "--report-out",
        help="Printable HTML checklist path. Default: next to the JSON runbook.",
    )
    dr_generate.add_argument(
        "--title",
        default=f"{APP_DISPLAY_NAME} Disaster Recovery Runbook",
    )
    dr_generate.set_defaults(func=command_dr_generate)

    dr_status = dr_sub.add_parser(
        "status",
        help="Show checklist completion, blockers, capabilities, and evidence.",
    )
    dr_status.add_argument("--runbook", required=True)
    dr_status.add_argument(
        "--status",
        action="append",
        choices=DR_CHECKLIST_STATUSES,
        help="Filter by checklist status; repeat as needed.",
    )
    dr_status.add_argument(
        "--allow-missing-source",
        action="store_true",
        help="Verify the portable runbook without requiring its original backup path.",
    )
    _add_output_arguments(dr_status)
    dr_status.set_defaults(func=command_dr_status)

    dr_check = dr_sub.add_parser(
        "check",
        help="Record one auditable checklist status change and regenerate HTML.",
    )
    dr_check.add_argument("--runbook", required=True)
    dr_check.add_argument("--item", required=True, help="Checklist item ID or unique prefix.")
    dr_check.add_argument("--status", required=True, choices=DR_CHECKLIST_STATUSES)
    dr_check.add_argument("--actor", required=True, help="Operator recording the decision.")
    dr_check.add_argument(
        "--evidence",
        default="",
        help="Non-secret ticket, artifact, report, or test reference.",
    )
    dr_check.add_argument("--note", default="", help="Decision or blocker note; never include secrets.")
    dr_check.add_argument(
        "--report-out",
        help="Updated HTML path. Default: runbook path with an .html suffix.",
    )
    dr_check.set_defaults(func=command_dr_check)

    dr_report = dr_sub.add_parser(
        "report",
        help="Regenerate printable HTML from a verified runbook.",
    )
    dr_report.add_argument("--runbook", required=True)
    dr_report.add_argument("--out", required=True)
    dr_report.add_argument(
        "--allow-missing-source",
        action="store_true",
        help="Verify the portable runbook without requiring its original backup path.",
    )
    dr_report.set_defaults(func=command_dr_report)

    dr_verify = dr_sub.add_parser(
        "verify",
        help="Verify source, plan, checklist state, event chain, and summary hashes.",
    )
    dr_verify.add_argument("--runbook", required=True)
    dr_verify.add_argument(
        "--allow-missing-source",
        action="store_true",
        help="Verify the portable runbook without requiring its original backup path.",
    )
    dr_verify.set_defaults(func=command_dr_verify)

    snapshot = sub.add_parser("snapshot", help="Manage the local credential-free snapshot catalog.")
    snapshot_sub = snapshot.add_subparsers(dest="snapshot_command", required=True)

    snapshot_list = snapshot_sub.add_parser("list", help="List registered snapshots.")
    snapshot_list.add_argument("--limit", type=int, default=100)
    _add_output_arguments(snapshot_list)
    snapshot_list.set_defaults(func=command_snapshot_list)

    snapshot_import = snapshot_sub.add_parser("import", help="Validate and register an existing backup.")
    snapshot_import.add_argument("path")
    snapshot_import.set_defaults(func=command_snapshot_import)

    snapshot_show = snapshot_sub.add_parser("show", help="Show snapshot metadata and resource counts.")
    snapshot_show.add_argument("snapshot", help="Snapshot ID, unique prefix, or latest.")
    snapshot_show.set_defaults(func=command_snapshot_show)

    snapshot_verify = snapshot_sub.add_parser("verify", help="Verify artifact and backup content hashes.")
    snapshot_verify.add_argument("snapshot", help="Snapshot ID, unique prefix, or latest.")
    snapshot_verify.set_defaults(func=command_snapshot_verify)

    inventory = sub.add_parser("inventory", help="Browse, search, and compare indexed snapshot metadata.")
    inventory_sub = inventory.add_subparsers(dest="inventory_command", required=True)

    inventory_list = inventory_sub.add_parser("list", help="List resources in a snapshot.")
    inventory_list.add_argument("--snapshot", default="latest", help="Snapshot ID/prefix, latest, or all.")
    inventory_list.add_argument("--resource-type")
    inventory_list.add_argument("--search")
    inventory_list.add_argument("--limit", type=int, default=500)
    inventory_list.add_argument(
        "--restore-commands",
        action="store_true",
        help="Print a copyable selective restore-plan command for each writable match.",
    )
    _add_output_arguments(inventory_list)
    inventory_list.set_defaults(func=command_inventory_list)

    inventory_search = inventory_sub.add_parser("search", help="Search resource names and stable keys.")
    inventory_search.add_argument("query")
    inventory_search.add_argument("--snapshot", default="all", help="Snapshot ID/prefix, latest, or all.")
    inventory_search.add_argument("--resource-type")
    inventory_search.add_argument("--limit", type=int, default=500)
    inventory_search.add_argument(
        "--restore-commands",
        action="store_true",
        help="Print a copyable selective restore-plan command for each writable match.",
    )
    _add_output_arguments(inventory_search)
    inventory_search.set_defaults(func=command_inventory_search)

    inventory_history = inventory_sub.add_parser("history", help="Show one resource across snapshots.")
    inventory_history.add_argument("--resource-type", required=True)
    inventory_history.add_argument("--stable-key", required=True)
    inventory_history.add_argument("--limit", type=int, default=100)
    _add_output_arguments(inventory_history)
    inventory_history.set_defaults(func=command_inventory_history)

    inventory_references = inventory_sub.add_parser(
        "references", help="Show outgoing or incoming resource references."
    )
    inventory_references.add_argument("--snapshot", default="latest")
    inventory_references.add_argument("--resource-type")
    inventory_references.add_argument("--stable-key")
    inventory_references.add_argument("--direction", choices=("outgoing", "incoming"), default="outgoing")
    inventory_references.add_argument("--limit", type=int, default=500)
    _add_output_arguments(inventory_references)
    inventory_references.set_defaults(func=command_inventory_references)

    inventory_drift = inventory_sub.add_parser("drift", help="Compare indexed resource configuration hashes.")
    inventory_drift.add_argument("--from", dest="from_snapshot", required=True, help="Older snapshot ID/prefix.")
    inventory_drift.add_argument("--to", dest="to_snapshot", required=True, help="Newer snapshot ID/prefix or latest.")
    inventory_drift.add_argument("--include-unchanged", action="store_true")
    _add_output_arguments(inventory_drift)
    inventory_drift.set_defaults(func=command_inventory_drift)

    audit = sub.add_parser("audit", help="Inspect and verify the tamper-evident run ledger.")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)

    audit_list = audit_sub.add_parser("list", help="List recorded workflow runs.")
    audit_list.add_argument("--limit", type=int, default=100)
    _add_output_arguments(audit_list)
    audit_list.set_defaults(func=command_audit_list)

    audit_failures = audit_sub.add_parser("failures", help="List failed workflow runs.")
    audit_failures.add_argument("--limit", type=int, default=100)
    _add_output_arguments(audit_failures)
    audit_failures.set_defaults(func=command_audit_failures)

    audit_summary = audit_sub.add_parser("summary", help="Summarize results by command.")
    _add_output_arguments(audit_summary)
    audit_summary.set_defaults(func=command_audit_summary)

    audit_show = audit_sub.add_parser("show", help="Show all events for one run.")
    audit_show.add_argument("run", help="Run ID or unique prefix.")
    audit_show.set_defaults(func=command_audit_show)

    audit_verify = audit_sub.add_parser("verify", help="Verify event hashes, ordering, and head checkpoint.")
    audit_verify.set_defaults(func=command_audit_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.policy_type = effective_policy_types(args.policy_type)
    invalid = sorted(set(args.policy_type) - set(POLICY_TYPES))
    if invalid:
        parser.error(f"unsupported policy type(s): {', '.join(invalid)}")
    configure_audit(args)
    try:
        configure_run_ledger(args)
        record_declared_inputs(args)
        args.func(args)
        args.audit_logger.log_event("run.finish", command=args.command, exit_code=0)
        finish_run_ledger(args, exit_code=0)
        return 0
    except CliError as error:
        safe_error = redact_text(str(error))
        args.audit_logger.log_event("run.finish", command=args.command, exit_code=1, error=safe_error)
        try:
            finish_run_ledger(args, exit_code=1, error=safe_error)
        except CliError as ledger_error:
            print(f"Audit ledger error: {ledger_error}", file=sys.stderr)
        print(f"Error: {safe_error}", file=sys.stderr)
        return 1
    except Exception as error:  # Last-resort run closure for filesystem/runtime failures.
        safe_error = redact_text(f"{type(error).__name__}: {error}")
        args.audit_logger.log_event("run.finish", command=args.command, exit_code=1, error=safe_error)
        try:
            finish_run_ledger(args, exit_code=1, error=safe_error)
        except Exception as ledger_error:
            print(f"Audit ledger error: {redact_text(str(ledger_error))}", file=sys.stderr)
        print(f"Error: {safe_error}", file=sys.stderr)
        return 1


__all__ = [name for name in globals() if not name.startswith("_")]
