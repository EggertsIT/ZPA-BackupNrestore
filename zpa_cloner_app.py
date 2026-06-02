#!/usr/bin/env python3
"""Local desktop UI for the ZPA backup and restore workflow."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from zpa_resources import POLICY_TYPES


PROJECT_DIR = Path(__file__).resolve().parent
CLI_PATH = PROJECT_DIR / "zpa_cloner.py"
APP_DISPLAY_NAME = "ZPA-Backup and Restore"
APP_WORK_DIR_NAME = APP_DISPLAY_NAME
DEFAULT_REPORT_NAME = "zpa-backup-restore-report.html"
DEFAULT_LEGACY_ZPA_BASE_URL = "https://config.private.zscaler.com"
DEFAULT_ONEAPI_BASE_URL = "https://api.zsapi.net"


def running_from_macos_bundle(path: Path | None = None) -> bool:
    path = path or PROJECT_DIR
    return path.name == "Resources" and path.parent.name == "Contents" and path.parent.parent.suffix == ".app"


def default_work_dir(path: Path | None = None) -> Path:
    if running_from_macos_bundle(path):
        return Path.home() / "Documents" / APP_WORK_DIR_NAME
    return path or PROJECT_DIR


WORK_DIR = default_work_dir()

SOURCE_ENV = (
    "ZPA_SOURCE_CLIENT_ID",
    "ZPA_SOURCE_CLIENT_SECRET",
    "ZPA_SOURCE_CUSTOMER_ID",
)
TARGET_ENV = (
    "ZPA_TARGET_CLIENT_ID",
    "ZPA_TARGET_CLIENT_SECRET",
    "ZPA_TARGET_CUSTOMER_ID",
)

PROFILE_PREFIXES = {
    "source": "ZPA_SOURCE_",
    "target": "ZPA_TARGET_",
}

PROFILE_LABELS = {
    "source": "Source",
    "target": "Destination",
}

CREDENTIAL_FIELDS = (
    ("AUTH_MODE", "API Mode", True, False),
    ("CLIENT_ID", "Client ID", True, False),
    ("CLIENT_SECRET", "Client Secret", True, True),
    ("CUSTOMER_ID", "Customer ID", True, False),
    ("ZPA_BASE_URL", "Legacy ZPA URL", False, False),
    ("ZIDENTITY_BASE_URL", "ZIdentity URL", False, False),
    ("ONEAPI_BASE_URL", "OneAPI URL", False, False),
    ("MICROTENANT_ID", "Microtenant ID", False, False),
)

ARTIFACT_LABELS = {
    "source backup": "source_backup",
    "target backup": "target_backup",
    "diff": "diff",
    "diff written": "diff",
    "report": "report",
    "report written": "report",
    "restore result": "apply_result",
    "apply result": "apply_result",
}


def parse_env_lines(lines: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(path: Path, *, overwrite: bool = False) -> list[str]:
    if not path.exists():
        return []
    values = parse_env_lines(path.read_text(encoding="utf-8").splitlines())
    loaded = []
    for key, value in values.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def env_file_candidates() -> list[Path]:
    candidates = [WORK_DIR / ".env"]
    if PROJECT_DIR != WORK_DIR:
        candidates.append(PROJECT_DIR / ".env")
    return candidates


def load_env_files(paths: Iterable[Path], *, overwrite: bool = False) -> list[str]:
    loaded: list[str] = []
    for path in paths:
        loaded.extend(load_env_file(path, overwrite=overwrite))
    return loaded


def parse_policy_types(text: str) -> list[str]:
    values = [value.strip().upper() for value in re.split(r"[\s,]+", text) if value.strip()]
    return values or list(POLICY_TYPES)


def build_policy_args(text: str) -> list[str]:
    args: list[str] = []
    for policy_type in parse_policy_types(text):
        args.extend(["--policy-type", policy_type])
    return args


def credential_env_name(profile: str, field_name: str) -> str:
    return f"{PROFILE_PREFIXES[profile]}{field_name}"


def auth_mode_for_profile(profile: str, env_values: dict[str, str]) -> str:
    mode = env_values.get(credential_env_name(profile, "AUTH_MODE"), "legacy").strip().casefold()
    return mode if mode in {"legacy", "oneapi"} else "legacy"


def required_env_for_profile(profile: str, env_values: dict[str, str]) -> list[str]:
    required = [
        credential_env_name(profile, "CLIENT_ID"),
        credential_env_name(profile, "CLIENT_SECRET"),
        credential_env_name(profile, "CUSTOMER_ID"),
    ]
    if auth_mode_for_profile(profile, env_values) == "oneapi":
        required.append(credential_env_name(profile, "ZIDENTITY_BASE_URL"))
    return required


def missing_env(names: Iterable[str], env_values: dict[str, str] | None = None) -> list[str]:
    values = env_values if env_values is not None else os.environ
    return [name for name in names if not values.get(name)]


def extract_artifact(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    lowered = stripped.lower()
    for label, key in ARTIFACT_LABELS.items():
        prefix = f"{label}:"
        if lowered.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            if value:
                return key, value
    return None


def status_from_line(line: str) -> str | None:
    stripped = line.strip()
    lowered = stripped.lower()
    if lowered.startswith("backup source:"):
        return f"Backing up source: {stripped.split(':', 1)[1].strip()}"
    if lowered.startswith("backup target:"):
        return f"Backing up target: {stripped.split(':', 1)[1].strip()}"
    if lowered.startswith("resource"):
        return "Building summary"
    if "preflight passed" in lowered:
        return "Preflight passed"
    if "preflight failed" in lowered:
        return "Preflight failed"
    if lowered.startswith(("create", "update", "delete")):
        parts = stripped.split()
        if len(parts) >= 3:
            return f"{parts[0].title()} {parts[1]}: {parts[2]}"
    artifact = extract_artifact(stripped)
    if artifact:
        return f"Captured {artifact[0].replace('_', ' ')}"
    return None


class ZPAClonerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_DISPLAY_NAME)
        self.root.geometry("1180x780")
        self.root.minsize(1040, 700)

        WORK_DIR.mkdir(parents=True, exist_ok=True)
        self.env_paths = env_file_candidates()
        self.startup_env_loaded = load_env_files(self.env_paths)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.worker: threading.Thread | None = None
        self.command_running = False

        self.source_backup_var = tk.StringVar()
        self.target_backup_var = tk.StringVar()
        self.diff_var = tk.StringVar()
        self.report_var = tk.StringVar()
        self.apply_result_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.detail_var = tk.StringVar(value="Ready")
        self.strict_manifest_var = tk.BooleanVar(value=True)
        self.allow_delete_var = tk.BooleanVar(value=False)
        self.allow_high_impact_var = tk.BooleanVar(value=False)
        self.allow_failed_backups_var = tk.BooleanVar(value=False)
        self.ignore_preflight_var = tk.BooleanVar(value=False)
        self.policy_vars = {
            policy_type: tk.BooleanVar(value=True)
            for policy_type in POLICY_TYPES
        }
        self.show_secrets_var = tk.BooleanVar(value=False)
        self.credential_vars: dict[str, dict[str, tk.StringVar]] = self._credential_vars_from_env()
        self.secret_entries: list[ttk.Entry] = []

        self.command_buttons: list[ttk.Widget] = []

        self._build_styles()
        self._build_layout()
        self.refresh_env()
        self.root.after(100, self._poll_events)

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        font_family = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
        self.root.configure(bg="#f6f8fb")
        style.configure(".", font=(font_family, 11), background="#f6f8fb", foreground="#1f2933")
        style.configure("TFrame", background="#f6f8fb")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f6f8fb", foreground="#1f2933")
        style.configure("Panel.TLabel", background="#ffffff", foreground="#1f2933")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#64748b")
        style.configure("Title.TLabel", font=(font_family, 18, "bold"), background="#f6f8fb")
        style.configure("Status.TLabel", font=(font_family, 11, "bold"), background="#f6f8fb")
        style.configure("TLabelframe", background="#ffffff", bordercolor="#d8dee9", relief="solid")
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#1f2933", font=(font_family, 11, "bold"))
        style.configure("TButton", padding=(10, 7))
        style.configure("Primary.TButton", padding=(12, 8))
        style.configure("Danger.TButton", padding=(12, 8))
        style.configure("TCheckbutton", background="#ffffff", foreground="#1f2933")
        style.configure("Treeview", rowheight=26, background="#ffffff", fieldbackground="#ffffff", foreground="#1f2933")
        style.configure("Treeview.Heading", font=(font_family, 10, "bold"))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text=APP_DISPLAY_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        content = ttk.PanedWindow(outer, orient="horizontal")
        content.pack(fill="both", expand=True)

        left_shell = ttk.Frame(content, width=450)
        left = self._scrollable_frame(left_shell)
        right = ttk.Frame(content)
        content.add(left_shell, weight=0)
        content.add(right, weight=1)

        self._build_env_panel(left)
        self._build_credentials_panel(left)
        self._build_policy_panel(left)
        self._build_artifact_panel(left)
        self._build_safeguard_panel(left)
        self._build_action_panel(left)
        self._build_activity_panel(right)

    def _scrollable_frame(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(parent, highlightthickness=0, background="#f6f8fb")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")

        def update_scrollregion(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_width(event: tk.Event) -> None:
            canvas.itemconfigure(window, width=event.width)

        frame.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_width)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return frame

    def _build_env_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Environment", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        self.env_tree = ttk.Treeview(frame, columns=("scope", "state", "missing"), show="headings", height=5)
        self.env_tree.heading("scope", text="Scope")
        self.env_tree.heading("state", text="State")
        self.env_tree.heading("missing", text="Missing")
        self.env_tree.column("scope", width=85, stretch=False)
        self.env_tree.column("state", width=70, stretch=False)
        self.env_tree.column("missing", width=230, stretch=True)
        self.env_tree.pack(fill="x")

        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Reload .env", command=self.reload_env).pack(side="left")
        ttk.Button(row, text="Refresh", command=self.refresh_env).pack(side="left", padx=(8, 0))

    def _build_credentials_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Tenant Credentials", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="x")
        for profile in ("source", "target"):
            tab = ttk.Frame(notebook, style="Panel.TFrame", padding=8)
            notebook.add(tab, text=PROFILE_LABELS[profile])
            for field_name, label, _required, secret in CREDENTIAL_FIELDS:
                self._credential_row(tab, profile, field_name, label, secret)

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Import Env", command=self.import_credentials_from_env).pack(side="left")
        ttk.Button(buttons, text="Copy to Dest", command=self.copy_source_to_destination).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Clear", command=self.clear_credentials).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            buttons,
            text="Show secrets",
            variable=self.show_secrets_var,
            command=self.refresh_secret_visibility,
        ).pack(side="right")

    def _build_policy_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Policy Rule Types", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        checks = ttk.Frame(frame, style="Panel.TFrame")
        checks.pack(fill="x")
        for policy_type in POLICY_TYPES:
            ttk.Checkbutton(
                checks,
                text=policy_type.replace("_", " "),
                variable=self.policy_vars[policy_type],
            ).pack(anchor="w", pady=1)

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Access Only", command=self.select_access_only).pack(side="left")
        ttk.Button(buttons, text="All Rule Types", command=self.select_all_policies).pack(side="left", padx=(8, 0))

    def _build_artifact_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Artifacts", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        self._path_row(frame, "Desired backup", self.source_backup_var, "json")
        self._path_row(frame, "Destination backup", self.target_backup_var, "json")
        self._path_row(frame, "Restore diff", self.diff_var, "json")
        self._path_row(frame, "Report", self.report_var, "html")
        self._path_row(frame, "Restore result", self.apply_result_var, "json")

    def _build_safeguard_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Restore Safeguards", padding=10)
        frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(frame, text="Strict manifest validation", variable=self.strict_manifest_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="Allow deletes", variable=self.allow_delete_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="Allow high-impact resources", variable=self.allow_high_impact_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="Allow backups with endpoint errors", variable=self.allow_failed_backups_var).pack(anchor="w")
        ttk.Checkbutton(frame, text="Bypass preflight block", variable=self.ignore_preflight_var).pack(anchor="w")

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Workflow", padding=10)
        frame.pack(fill="x")

        backup = ttk.LabelFrame(frame, text="1. Create / Compare Backups", padding=8)
        backup.pack(fill="x")
        backup_row_1 = ttk.Frame(backup, style="Panel.TFrame")
        backup_row_1.pack(fill="x")
        self._action_button(backup_row_1, "Backup Source", self.run_backup_source).pack(side="left", fill="x", expand=True)
        self._action_button(backup_row_1, "Backup Destination", self.run_backup_target).pack(side="left", fill="x", expand=True, padx=(8, 0))
        backup_row_2 = ttk.Frame(backup, style="Panel.TFrame")
        backup_row_2.pack(fill="x", pady=(8, 0))
        self._action_button(backup_row_2, "Compare Source to Destination", self.run_plan, style="Primary.TButton").pack(side="left", fill="x", expand=True)

        restore = ttk.LabelFrame(frame, text="2. Restore Destination", padding=8)
        restore.pack(fill="x", pady=(10, 0))
        restore_row_1 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_1.pack(fill="x")
        self._action_button(restore_row_1, "Choose Desired Backup", self.choose_desired_backup).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_1, "Build Restore Plan", self.run_restore_plan, style="Primary.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))
        restore_row_2 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_2.pack(fill="x", pady=(8, 0))
        self._action_button(restore_row_2, "Validate", self.run_validate).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_2, "Preflight", self.run_preflight).pack(side="left", fill="x", expand=True, padx=(8, 0))
        restore_row_3 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_3.pack(fill="x", pady=(8, 0))
        self._action_button(restore_row_3, "Dry Run", self.run_restore_dry).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_3, "Restore", self.run_restore, style="Danger.TButton").pack(side="left", fill="x", expand=True, padx=(8, 0))

        utilities = ttk.LabelFrame(frame, text="3. Review", padding=8)
        utilities.pack(fill="x", pady=(10, 0))
        utility_row = ttk.Frame(utilities, style="Panel.TFrame")
        utility_row.pack(fill="x")
        self._action_button(utility_row, "Report", self.run_report).pack(side="left", fill="x", expand=True)
        self._action_button(utility_row, "Coverage", self.run_coverage).pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _build_activity_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Activity", padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.detail_var, style="Panel.TLabel").pack(side="left", fill="x", expand=True)
        self.stop_button = ttk.Button(top, text="Stop", command=self.stop_command, state="disabled")
        self.stop_button.pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Open Report", command=self.open_report).pack(side="right")

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(10, 8))

        self.log = scrolledtext.ScrolledText(
            frame,
            height=28,
            wrap="word",
            bg="#0f172a",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            selectbackground="#334155",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log.configure(font=("Menlo" if sys.platform == "darwin" else "Consolas", 11))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    def _path_row(self, parent: ttk.Frame, label: str, var: tk.StringVar, kind: str) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="Panel.TLabel", width=18).pack(side="left")
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 6))
        command = self._save_file if label == "Report" else self._open_file
        ttk.Button(row, text="Browse", command=lambda: command(var, kind)).pack(side="right")

    def _credential_row(self, parent: ttk.Frame, profile: str, field_name: str, label: str, secret: bool) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="Panel.TLabel", width=14).pack(side="left")
        if field_name == "AUTH_MODE":
            entry = ttk.Combobox(
                row,
                textvariable=self.credential_vars[profile][field_name],
                values=("legacy", "oneapi"),
                state="readonly",
            )
        else:
            entry = ttk.Entry(
                row,
                textvariable=self.credential_vars[profile][field_name],
                show="*" if secret and not self.show_secrets_var.get() else "",
            )
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        if secret:
            self.secret_entries.append(entry)

    def _action_button(self, parent: ttk.Frame, text: str, command, style: str = "TButton") -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style=style)
        self.command_buttons.append(button)
        return button

    def reload_env(self) -> None:
        loaded = load_env_files(self.env_paths, overwrite=True)
        self.import_credentials_from_env(log=False)
        self.refresh_env()
        if loaded:
            self._append_log(f"loaded .env keys: {', '.join(sorted(loaded))}")
            self.detail_var.set(f"Loaded {len(loaded)} .env value(s)")
        else:
            checked = ", ".join(str(path) for path in self.env_paths)
            self._append_log(f"no .env values loaded; checked {checked}")
            self.detail_var.set("No .env values loaded")

    def refresh_env(self) -> None:
        for item in self.env_tree.get_children():
            self.env_tree.delete(item)
        env_values = self.effective_env()
        source_missing = missing_env(required_env_for_profile("source", env_values), env_values)
        target_missing = missing_env(required_env_for_profile("target", env_values), env_values)
        source_mode = auth_mode_for_profile("source", env_values)
        target_mode = auth_mode_for_profile("target", env_values)
        self.env_tree.insert("", "end", values=("Source", "OK" if not source_missing else "Missing", f"{source_mode}; {', '.join(source_missing)}"))
        self.env_tree.insert("", "end", values=("Destination", "OK" if not target_missing else "Missing", f"{target_mode}; {', '.join(target_missing)}"))
        oneapi = env_values.get("ZPA_SOURCE_ONEAPI_BASE_URL") or env_values.get("ZPA_TARGET_ONEAPI_BASE_URL")
        oneapi = oneapi or env_values.get("ZSCALER_ONEAPI_BASE_URL") or DEFAULT_ONEAPI_BASE_URL
        zpa_base = env_values.get("ZPA_SOURCE_ZPA_BASE_URL") or env_values.get("ZPA_TARGET_ZPA_BASE_URL")
        zpa_base = zpa_base or env_values.get("ZSCALER_ZPA_BASE_URL") or DEFAULT_LEGACY_ZPA_BASE_URL
        self.env_tree.insert("", "end", values=("ZPA API", "OK", zpa_base if source_mode == "legacy" or target_mode == "legacy" else oneapi))
        env_files = [str(path) for path in self.env_paths if path.exists()]
        self.env_tree.insert("", "end", values=("Env File", "OK" if env_files else "Missing", ", ".join(env_files)))
        self.env_tree.insert("", "end", values=("Work Dir", "OK", str(WORK_DIR)))

    def _credential_vars_from_env(self) -> dict[str, dict[str, tk.StringVar]]:
        values: dict[str, dict[str, tk.StringVar]] = {}
        for profile in PROFILE_PREFIXES:
            values[profile] = {}
            for field_name, _label, _required, _secret in CREDENTIAL_FIELDS:
                env_name = credential_env_name(profile, field_name)
                default = ""
                if field_name == "AUTH_MODE":
                    default = os.environ.get(env_name, os.environ.get("ZSCALER_AUTH_MODE", "legacy"))
                elif field_name == "ZPA_BASE_URL":
                    default = os.environ.get(env_name, os.environ.get("ZSCALER_ZPA_BASE_URL", DEFAULT_LEGACY_ZPA_BASE_URL))
                elif field_name == "ONEAPI_BASE_URL":
                    default = os.environ.get(env_name, os.environ.get("ZSCALER_ONEAPI_BASE_URL", ""))
                else:
                    default = os.environ.get(env_name, "")
                values[profile][field_name] = tk.StringVar(value=default)
        return values

    def credential_env(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for profile, fields in self.credential_vars.items():
            for field_name, var in fields.items():
                value = var.get().strip()
                if value:
                    values[credential_env_name(profile, field_name)] = value
        return values

    def effective_env(self) -> dict[str, str]:
        values = os.environ.copy()
        for profile in PROFILE_PREFIXES:
            for field_name, _label, _required, _secret in CREDENTIAL_FIELDS:
                values.pop(credential_env_name(profile, field_name), None)
        values.update(self.credential_env())
        return values

    def import_credentials_from_env(self, *, log: bool = True) -> None:
        imported = 0
        for profile in PROFILE_PREFIXES:
            for field_name, _label, _required, _secret in CREDENTIAL_FIELDS:
                env_name = credential_env_name(profile, field_name)
                value = os.environ.get(env_name)
                if not value and field_name == "AUTH_MODE":
                    value = os.environ.get("ZSCALER_AUTH_MODE")
                if not value and field_name == "ZPA_BASE_URL":
                    value = os.environ.get("ZSCALER_ZPA_BASE_URL")
                if not value and field_name == "ONEAPI_BASE_URL":
                    value = os.environ.get("ZSCALER_ONEAPI_BASE_URL")
                if value:
                    self.credential_vars[profile][field_name].set(value)
                    imported += 1
        self.refresh_env()
        if log:
            self._append_log(f"imported {imported} credential field(s) from environment")
            self.detail_var.set(f"Imported {imported} credential field(s)")

    def copy_source_to_destination(self) -> None:
        for field_name, _label, _required, _secret in CREDENTIAL_FIELDS:
            self.credential_vars["target"][field_name].set(self.credential_vars["source"][field_name].get())
        self.refresh_env()
        self._append_log("copied source credential fields to destination")
        self.detail_var.set("Copied source credentials to destination")

    def clear_credentials(self) -> None:
        for fields in self.credential_vars.values():
            for var in fields.values():
                var.set("")
        for profile in PROFILE_PREFIXES:
            self.credential_vars[profile]["AUTH_MODE"].set("legacy")
            self.credential_vars[profile]["ZPA_BASE_URL"].set(DEFAULT_LEGACY_ZPA_BASE_URL)
        self.refresh_env()
        self._append_log("cleared credential fields")
        self.detail_var.set("Credential fields cleared")

    def refresh_secret_visibility(self) -> None:
        show = "" if self.show_secrets_var.get() else "*"
        for entry in self.secret_entries:
            entry.configure(show=show)

    def select_access_only(self) -> None:
        for policy_type, var in self.policy_vars.items():
            var.set(policy_type == "ACCESS_POLICY")

    def select_all_policies(self) -> None:
        for var in self.policy_vars.values():
            var.set(True)

    def selected_policy_types(self) -> list[str]:
        return [policy_type for policy_type, var in self.policy_vars.items() if var.get()]

    def selected_policy_text(self) -> str:
        return ",".join(self.selected_policy_types())

    def policy_args(self) -> list[str]:
        args: list[str] = []
        for policy_type in self.selected_policy_types():
            args.extend(["--policy-type", policy_type])
        return args

    def ensure_policy_scope(self) -> bool:
        if not self.selected_policy_types():
            self._show_error("Select at least one policy type.")
            return False
        return True

    def run_backup_source(self) -> None:
        if not self.ensure_policy_scope():
            return
        if not self._require_profiles("backup source", ("source",)):
            return
        self._run_command("Backup Source", self.policy_args() + ["backup", "source"])

    def run_backup_target(self) -> None:
        if not self.ensure_policy_scope():
            return
        if not self._require_profiles("backup destination", ("target",)):
            return
        self._run_command("Backup Destination", self.policy_args() + ["backup", "target"])

    def choose_desired_backup(self) -> None:
        self._open_file(self.source_backup_var, "json")

    def run_plan(self) -> None:
        if not self.ensure_policy_scope():
            return
        if not self._require_profiles("plan", ("source", "target")):
            return
        self._run_command("Compare Source to Destination", self.policy_args() + ["plan"])

    def run_restore_plan(self) -> None:
        source_backup = self.source_backup_var.get().strip()
        if not source_backup:
            self._show_error("Select the desired backup snapshot first.")
            return
        if not self._require_profiles("restore from backup", ("target",)):
            return
        args = [*self.policy_args(), "restore-plan", "--source-backup", source_backup]
        if not self.strict_manifest_var.get():
            args.append("--allow-invalid-backup")
        self._run_command("Restore From Backup", args)

    def run_validate(self) -> None:
        args = ["validate"]
        if self.source_backup_var.get().strip():
            args.extend(["--backup", self.source_backup_var.get().strip()])
        if self.target_backup_var.get().strip():
            args.extend(["--backup", self.target_backup_var.get().strip()])
        if self.diff_var.get().strip():
            args.extend(["--diff", self.diff_var.get().strip()])
        if self.strict_manifest_var.get():
            args.append("--strict-manifest")
        if args == ["validate"] or args == ["validate", "--strict-manifest"]:
            self._show_error("Select at least one backup or diff file first.")
            return
        self._run_command("Validate", args)

    def run_preflight(self) -> None:
        paths = self._restore_paths()
        if not paths:
            return
        args = [
            "preflight",
            "--source-backup",
            paths["source_backup"],
            "--target-backup",
            paths["target_backup"],
            "--diff",
            paths["diff"],
        ]
        if self.allow_failed_backups_var.get():
            args.append("--allow-failed-backups")
        self._run_command("Preflight", args)

    def run_restore_dry(self) -> None:
        if not self._require_profiles("dry run restore", ("target",)):
            return
        paths = self._restore_paths()
        if not paths:
            return
        self._run_command("Dry Run Restore", self._restore_args(paths, dry_run=True))

    def run_restore(self) -> None:
        if not self._require_profiles("restore", ("target",)):
            return
        paths = self._restore_paths()
        if not paths:
            return
        if not messagebox.askyesno("Confirm Restore", "Run restore against the target tenant with --yes?"):
            return
        self._run_command("Restore", self._restore_args(paths, dry_run=False))

    def run_report(self) -> None:
        args = ["report", "--title", f"{APP_DISPLAY_NAME} UI Report"]
        if self.source_backup_var.get().strip():
            args.extend(["--source-backup", self.source_backup_var.get().strip()])
        if self.target_backup_var.get().strip():
            args.extend(["--target-backup", self.target_backup_var.get().strip()])
        if self.diff_var.get().strip():
            args.extend(["--diff", self.diff_var.get().strip()])
        if self.apply_result_var.get().strip():
            args.extend(["--apply-result", self.apply_result_var.get().strip()])
        report_path = self.report_var.get().strip()
        if not report_path:
            report_path = self._default_report_path()
            self.report_var.set(report_path)
        args.extend(["--out", report_path])
        self._run_command("Report", args)

    def run_coverage(self) -> None:
        self._run_command("Coverage", ["coverage"])

    def _restore_paths(self) -> dict[str, str] | None:
        paths = {
            "source_backup": self.source_backup_var.get().strip(),
            "target_backup": self.target_backup_var.get().strip(),
            "diff": self.diff_var.get().strip(),
        }
        missing = [name.replace("_", " ") for name, value in paths.items() if not value]
        if missing:
            self._show_error(f"Select required restore files first: {', '.join(missing)}.")
            return None
        return paths

    def _restore_args(self, paths: dict[str, str], *, dry_run: bool) -> list[str]:
        args = [
            "restore",
            "--source-backup",
            paths["source_backup"],
            "--target-backup",
            paths["target_backup"],
            "--diff",
            paths["diff"],
        ]
        if dry_run:
            args.append("--dry-run")
        else:
            args.append("--yes")
        if self.allow_delete_var.get():
            args.append("--allow-delete")
        if self.allow_high_impact_var.get():
            args.append("--allow-high-impact")
        if self.allow_failed_backups_var.get():
            args.append("--allow-failed-backups")
        if self.ignore_preflight_var.get():
            args.append("--ignore-preflight")
        return args

    def _require_env(self, action: str, names: Iterable[str]) -> bool:
        missing = missing_env(names, self.effective_env())
        if missing:
            self.refresh_env()
            self._show_error(f"Cannot run {action}. Missing environment values: {', '.join(missing)}.")
            return False
        return True

    def _require_profiles(self, action: str, profiles: Iterable[str]) -> bool:
        env_values = self.effective_env()
        names: list[str] = []
        for profile in profiles:
            names.extend(required_env_for_profile(profile, env_values))
        return self._require_env(action, names)

    def _run_command(self, label: str, args: list[str]) -> None:
        if self.command_running:
            self._show_error("A command is already running.")
            return
        command = [sys.executable, "-u", str(CLI_PATH), *args]
        run_env = self.effective_env()
        display = " ".join(self._quote_part(part) for part in command)
        self._append_log(f"$ {display}")
        self.command_running = True
        self.status_var.set(f"Running: {label}")
        self.detail_var.set(label)
        self._set_buttons_enabled(False)
        self.stop_button.configure(state="normal")
        self.progress.start(12)
        self.worker = threading.Thread(target=self._command_worker, args=(command, run_env), daemon=True)
        self.worker.start()

    def _command_worker(self, command: list[str], run_env: dict[str, str]) -> None:
        try:
            env = run_env.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                command,
                cwd=str(WORK_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.process = process
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(("line", line.rstrip("\n")))
            return_code = process.wait()
            self.events.put(("done", return_code))
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            self.process = None

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    self._handle_line(str(payload))
                elif kind == "done":
                    self._finish_command(int(payload))
                elif kind == "error":
                    self._append_log(f"ui error: {payload}")
                    self._finish_command(1)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_line(self, line: str) -> None:
        self._append_log(line)
        artifact = extract_artifact(line)
        if artifact:
            key, value = artifact
            self._set_artifact(key, value)
        status = status_from_line(line)
        if status:
            self.detail_var.set(status)

    def _finish_command(self, return_code: int) -> None:
        self.progress.stop()
        self.command_running = False
        self._set_buttons_enabled(True)
        self.stop_button.configure(state="disabled")
        if return_code == 0:
            self.status_var.set("Complete")
            self.detail_var.set("Command completed")
            self._append_log("command completed")
        else:
            self.status_var.set("Failed")
            self.detail_var.set(f"Command failed with exit code {return_code}")
            self._append_log(f"command failed with exit code {return_code}")
        self.refresh_env()

    def stop_command(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self._append_log("stop requested")
            self.detail_var.set("Stopping command")

    def open_report(self) -> None:
        report = self.report_var.get().strip()
        if not report:
            self._show_error("No report file is selected.")
            return
        path = Path(report)
        if not path.is_absolute():
            path = WORK_DIR / path
        if not path.exists():
            self._show_error(f"Report file does not exist: {path}")
            return
        webbrowser.open(path.resolve().as_uri())

    def _set_artifact(self, key: str, value: str) -> None:
        path = Path(value)
        if not path.is_absolute():
            path = WORK_DIR / path
        target = {
            "source_backup": self.source_backup_var,
            "target_backup": self.target_backup_var,
            "diff": self.diff_var,
            "report": self.report_var,
            "apply_result": self.apply_result_var,
        }.get(key)
        if target is not None:
            target.set(str(path))

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.command_buttons:
            button.configure(state=state)

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_file(self, var: tk.StringVar, kind: str) -> None:
        filetypes = self._filetypes(kind)
        path = filedialog.askopenfilename(initialdir=str(WORK_DIR), filetypes=filetypes)
        if path:
            var.set(path)

    def _save_file(self, var: tk.StringVar, kind: str) -> None:
        filetypes = self._filetypes(kind)
        backups_dir = WORK_DIR / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(initialdir=str(backups_dir), filetypes=filetypes)
        if path:
            var.set(path)

    def _filetypes(self, kind: str) -> list[tuple[str, str]]:
        if kind == "html":
            return [("HTML files", "*.html"), ("All files", "*.*")]
        return [("JSON files", "*.json"), ("All files", "*.*")]

    def _default_report_path(self) -> str:
        diff = self.diff_var.get().strip()
        if diff:
            return str(Path(diff).with_suffix(".html"))
        return str(WORK_DIR / "backups" / DEFAULT_REPORT_NAME)

    def _show_error(self, message: str) -> None:
        self.detail_var.set(message)
        self._append_log(f"ui: {message}")
        messagebox.showerror(APP_DISPLAY_NAME, message)

    def _quote_part(self, value: str) -> str:
        if re.search(r"\s", value):
            return repr(value)
        return value


def main() -> int:
    root = tk.Tk()
    ZPAClonerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
