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
from typing import Callable, Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from zpa_resources import MIGRATION_ORDER, POLICY_TYPES


PROJECT_DIR = Path(__file__).resolve().parent
CLI_PATH = PROJECT_DIR / "zpa_cloner.py"
APP_DISPLAY_NAME = "ZPA-Backup and Restore"
APP_WORK_DIR_NAME = APP_DISPLAY_NAME
DEFAULT_REPORT_NAME = "zpa-backup-restore-report.html"
DEFAULT_LEGACY_ZPA_BASE_URL = "https://config.private.zscaler.com"
DEFAULT_ONEAPI_BASE_URL = "https://api.zsapi.net"
BACKUP_PASSPHRASE_ENV = "ZPA_BACKUP_PASSPHRASE"
DISCLAIMER_TEXT = (
    "Independent tool. Not affiliated with, endorsed by, sponsored by, certified by, or supported by "
    "Zscaler, Inc. Provided as is, without warranty or Zscaler support."
)
LEFT_PANEL_TABS = ("Workflow", "Tenants", "Options", "Scope", "Artifacts", "Status")
COMPACT_GRID_COLUMNS = 2

TAB_TOOLTIPS = {
    "Workflow": "Run the guided backup, restore, inventory, audit, and review actions.",
    "Tenants": "Configure Source credentials for reads and Destination credentials for restore writes.",
    "Options": "Choose backup policy coverage, encryption, and restore safety gates.",
    "Scope": "Limit a restore to named objects or whole writable resource types.",
    "Artifacts": "Select or inspect the backup, diff, simulation, report, result, and audit files.",
    "Status": "Check credential readiness, API mode, environment files, and the runtime directory.",
}

ACTION_TOOLTIPS = {
    "Backup Source": "Read the Source tenant and create a local configuration snapshot. This does not write to the tenant.",
    "Backup Destination": "Read the Destination tenant and create a local configuration snapshot. This does not write to the tenant.",
    "Compare Source to Destination": "Back up both tenants, calculate their differences, and create JSON and HTML reports without writing to either tenant.",
    "Choose Desired Backup": "Select the snapshot that represents the configuration you want the Destination tenant to have.",
    "Build Restore Plan": "Read the current Destination tenant and compare it with the desired backup. No configuration is changed.",
    "Validate": "Check selected backup manifests, checksums, schemas, and diff structure using local files only.",
    "Preflight": "Check tenant identities, backup errors, dependency order, and restore prerequisites before simulation or writes.",
    "Simulate": "Create an offline, ordered preview of every planned, skipped, or blocked restore operation. No tenant credentials or writes are used.",
    "Restore": "Verify the reviewed simulation and fresh Destination state, then apply approved writes only to the Destination tenant.",
    "Snapshots": "List backup snapshots registered in the local SQLite catalog.",
    "Latest Inventory": "List objects in the newest cataloged snapshot, including copyable selective-restore commands where supported.",
    "Audit Summary": "Summarize commands recorded in the tamper-evident local run ledger.",
    "Verify Ledger": "Verify the run ledger hash chain and report missing, modified, or reordered events.",
    "Report": "Generate an HTML report from the currently selected artifacts.",
    "Coverage": "Show modeled ZPA API resources, operations, safety roles, and known exclusions.",
}

SAFEGUARD_TOOLTIPS = {
    "Strict manifest": "Require backup manifests and valid checksums. Keep this enabled for normal validation and restore work.",
    "Allow deletes": "Permit planned deletions on the Destination tenant. Deletions are skipped when this is off.",
    "Allow high-impact": "Permit explicitly reviewed high-impact writes such as Microtenant or Application Segment move/share operations.",
    "Allow endpoint-error backups": "Allow planning from an incomplete backup that recorded API endpoint failures. Review missing data before enabling.",
    "Bypass preflight block": "Continue despite failed preflight checks. This weakens a restore safety gate and is intended only for exceptional recovery.",
}

CREDENTIAL_TOOLTIPS = {
    "AUTH_MODE": "Choose legacy for the classic ZPA API or oneapi for ZIdentity-based authentication.",
    "CLIENT_ID": "OAuth client identifier for this tenant profile.",
    "CLIENT_SECRET": "OAuth client secret for this tenant profile. It stays masked and is not written to logs.",
    "CUSTOMER_ID": "ZPA customer identifier used to address this tenant.",
    "ZPA_BASE_URL": "Base URL for legacy ZPA configuration API requests.",
    "ZIDENTITY_BASE_URL": "ZIdentity authentication URL required when API Mode is oneapi.",
    "ONEAPI_BASE_URL": "Zscaler OneAPI gateway URL used when API Mode is oneapi.",
    "MICROTENANT_ID": "Optional Microtenant scope. Leave empty to operate at the customer scope.",
}

ARTIFACT_TOOLTIPS = {
    "Desired backup": "The source or historical snapshot that defines the intended Destination configuration.",
    "Destination backup": "The reviewed snapshot of the Destination tenant used to calculate the restore diff.",
    "Restore diff": "The machine-readable set of creates, updates, deletes, skips, and selective scope.",
    "Report": "The HTML report path. Browse chooses where a new report will be saved.",
    "Reviewed simulation": "The reviewed simulation JSON required by default before live restore.",
    "Restore result": "The execution result and journal summary produced by a live restore.",
    "Audit log": "The detailed, sanitized HTTP audit log. Treat it as sensitive operational data.",
}


TooltipProvider = Callable[[tk.Event], str | None]


class ToolTip:
    """Delayed pointer- and keyboard-accessible tooltip for a Tk widget."""

    def __init__(
        self,
        widget: tk.Misc,
        text: str | TooltipProvider,
        *,
        delay_ms: int = 550,
        wraplength: int = 360,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        self._current_text: str | None = None

        widget.bind("<Enter>", self._queue, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<FocusIn>", self._queue, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")
        widget.bind("<Destroy>", self._destroy, add="+")
        if callable(text):
            widget.bind("<Motion>", self._queue, add="+")

    def _resolve_text(self, event: tk.Event) -> str | None:
        if callable(self.text):
            return self.text(event)
        return self.text

    def _queue(self, event: tk.Event) -> None:
        text = self._resolve_text(event)
        if not text:
            self._hide()
            return
        if text == self._current_text and (self._after_id or self._window):
            return
        self._cancel()
        self._close_window()
        self._current_text = text
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _show(self) -> None:
        self._after_id = None
        if not self._current_text or not self.widget.winfo_viewable():
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        try:
            window.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            window,
            text=self._current_text,
            justify="left",
            wraplength=self.wraplength,
            background="#172033",
            foreground="#f8fafc",
            relief="solid",
            borderwidth=1,
            padx=9,
            pady=7,
        )
        label.pack()
        window.update_idletasks()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        x = min(x, self.widget.winfo_screenwidth() - window.winfo_reqwidth() - 8)
        y = min(y, self.widget.winfo_screenheight() - window.winfo_reqheight() - 8)
        window.wm_geometry(f"+{max(8, x)}+{max(8, y)}")
        self._window = window

    def _cancel(self) -> None:
        if self._after_id is None:
            return
        try:
            self.widget.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _close_window(self) -> None:
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
        self._window = None

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._close_window()
        self._current_text = None

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self.widget:
            self._hide()


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
    "audit log": "audit_log",
    "source backup": "source_backup",
    "target backup": "target_backup",
    "diff": "diff",
    "diff written": "diff",
    "report": "report",
    "report written": "report",
    "restore result": "apply_result",
    "apply result": "apply_result",
    "simulation": "simulation",
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


def build_encryption_args(encrypt_backups: bool) -> list[str]:
    return ["--encrypt-backups"] if encrypt_backups else []


def parse_restore_selectors(text: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"[\n,]+", text)
        if value.strip()
    ]


def build_restore_selection_args(
    selector_text: str,
    resource_types: Iterable[str],
    *,
    include_dependencies: bool,
    restore_policy_order: bool,
) -> list[str]:
    selectors = parse_restore_selectors(selector_text)
    selected_types = [value for value in resource_types if value]
    if not selectors and not selected_types:
        if include_dependencies or restore_policy_order:
            raise ValueError(
                "Dependency and policy-order options require an object or resource-type selection."
            )
        return []
    args: list[str] = []
    for selector in selectors:
        args.extend(["--select", selector])
    for resource_type in selected_types:
        args.extend(["--select-resource", resource_type])
    if include_dependencies:
        args.append("--include-dependencies")
    if restore_policy_order:
        args.append("--restore-policy-order")
    return args


def compact_grid_position(index: int, columns: int = COMPACT_GRID_COLUMNS) -> tuple[int, int]:
    if index < 0:
        raise ValueError("index must be non-negative")
    if columns < 1:
        raise ValueError("columns must be positive")
    return divmod(index, columns)


def policy_display_name(policy_type: str) -> str:
    return policy_type.removesuffix("_POLICY").replace("_", " ").title()


def resource_display_name(resource_type: str) -> str:
    return resource_type.replace("_", " ").title()


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
    if lowered.startswith("run:"):
        return stripped[4:].strip().capitalize()
    if lowered.startswith("api:"):
        return stripped[4:].strip()
    if lowered.startswith("backup source:"):
        return f"Backing up source: {stripped.split(':', 1)[1].strip()}"
    if lowered.startswith("backup target:"):
        return f"Backing up target: {stripped.split(':', 1)[1].strip()}"
    if lowered.startswith("backup ") and " warnings:" in lowered:
        return stripped
    if lowered.startswith("restore plan:"):
        return stripped
    if lowered.startswith(
        (
            "restore scope:",
            "scope selected:",
            "scope dependency:",
            "scope resource-type:",
        )
    ):
        return stripped
    if lowered.startswith("restore safeguards:"):
        return stripped
    if lowered.startswith("restore summary:"):
        return stripped
    if lowered.startswith("simulation summary:"):
        return stripped
    if lowered.startswith("simulation blocker:"):
        return stripped
    if lowered.startswith("resource"):
        return "Building summary"
    if "preflight passed" in lowered:
        return "Preflight passed"
    if "preflight failed" in lowered:
        return "Preflight failed"
    if lowered.startswith(("create", "update", "delete")):
        parts = stripped.split()
        if len(parts) >= 4 and parts[2] == "DRY-RUN":
            return f"Dry-run {parts[0].title()} {parts[1]}: {parts[3]}"
        if len(parts) >= 4:
            return f"{parts[0].title()} {parts[1]}: {parts[3]} ({parts[2]})"
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
        self.simulation_var = tk.StringVar()
        self.apply_result_var = tk.StringVar()
        self.audit_log_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.detail_var = tk.StringVar(value="Ready")
        self.strict_manifest_var = tk.BooleanVar(value=True)
        self.allow_delete_var = tk.BooleanVar(value=False)
        self.allow_high_impact_var = tk.BooleanVar(value=False)
        self.allow_failed_backups_var = tk.BooleanVar(value=False)
        self.ignore_preflight_var = tk.BooleanVar(value=False)
        self.encrypt_backups_var = tk.BooleanVar(value=False)
        self.backup_passphrase_var = tk.StringVar(value=os.environ.get(BACKUP_PASSPHRASE_ENV, ""))
        self.restore_selector_var = tk.StringVar()
        self.include_dependencies_var = tk.BooleanVar(value=False)
        self.restore_policy_order_var = tk.BooleanVar(value=False)
        self.restore_resource_vars = {
            resource_type: tk.BooleanVar(value=False)
            for resource_type in MIGRATION_ORDER
        }
        self.policy_vars = {
            policy_type: tk.BooleanVar(value=True)
            for policy_type in POLICY_TYPES
        }
        self.show_secrets_var = tk.BooleanVar(value=False)
        self.credential_vars: dict[str, dict[str, tk.StringVar]] = self._credential_vars_from_env()
        self.secret_entries: list[ttk.Entry] = []

        self.command_buttons: list[ttk.Widget] = []
        self.tooltips: list[ToolTip] = []

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
        style.configure("Disclaimer.TLabel", background="#f6f8fb", foreground="#7f1d1d")
        style.configure("Title.TLabel", font=(font_family, 18, "bold"), background="#f6f8fb")
        style.configure("Status.TLabel", font=(font_family, 11, "bold"), background="#f6f8fb")
        style.configure("TLabelframe", background="#ffffff", bordercolor="#d8dee9", relief="solid")
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#1f2933", font=(font_family, 11, "bold"))
        style.configure("TButton", padding=(8, 6))
        style.configure("Primary.TButton", padding=(10, 7))
        style.configure("Danger.TButton", padding=(10, 7))
        style.configure("TCheckbutton", background="#ffffff", foreground="#1f2933")
        style.configure("TNotebook", background="#f6f8fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(10, 6))
        style.configure("Treeview", rowheight=24, background="#ffffff", fieldbackground="#ffffff", foreground="#1f2933")
        style.configure("Treeview.Heading", font=(font_family, 10, "bold"))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text=APP_DISPLAY_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        ttk.Label(
            outer,
            text=DISCLAIMER_TEXT,
            style="Disclaimer.TLabel",
            wraplength=1080,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        content = ttk.PanedWindow(outer, orient="horizontal")
        content.pack(fill="both", expand=True)

        left_shell = ttk.Frame(content, width=480)
        right = ttk.Frame(content)
        content.add(left_shell, weight=0)
        content.add(right, weight=1)

        self.left_notebook = ttk.Notebook(left_shell)
        self.left_notebook.pack(fill="both", expand=True)
        self._add_notebook_tooltips(self.left_notebook, TAB_TOOLTIPS)
        tabs: dict[str, ttk.Frame] = {}
        for name in LEFT_PANEL_TABS:
            tab = ttk.Frame(self.left_notebook, style="Panel.TFrame", padding=8)
            self.left_notebook.add(tab, text=name)
            tabs[name] = tab

        self._build_action_panel(tabs["Workflow"])
        self._build_credentials_panel(tabs["Tenants"])
        self._build_policy_panel(tabs["Options"])
        self._build_backup_security_panel(tabs["Options"])
        self._build_safeguard_panel(tabs["Options"])
        self._build_restore_scope_panel(tabs["Scope"])
        self._build_artifact_panel(tabs["Artifacts"])
        self._build_env_panel(tabs["Status"])
        self._build_activity_panel(right)

    def _build_env_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Environment Readiness", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        self.env_tree = ttk.Treeview(frame, columns=("scope", "state", "missing"), show="headings", height=5)
        self.env_tree.heading("scope", text="Scope")
        self.env_tree.heading("state", text="State")
        self.env_tree.heading("missing", text="Missing")
        self.env_tree.column("scope", width=85, stretch=False)
        self.env_tree.column("state", width=70, stretch=False)
        self.env_tree.column("missing", width=230, stretch=True)
        self.env_tree.pack(fill="x")

        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        reload_button = ttk.Button(row, text="Reload .env", command=self.reload_env)
        reload_button.pack(side="left")
        self._add_tooltip(
            reload_button,
            "Reload values from the configured .env files and replace matching in-memory environment values.",
        )
        refresh_button = ttk.Button(row, text="Refresh", command=self.refresh_env)
        refresh_button.pack(side="left", padx=(6, 0))
        self._add_tooltip(
            refresh_button,
            "Recheck readiness using the credentials and environment values currently shown. No files or tenants are changed.",
        )
        self._add_tooltip(
            self.env_tree,
            "Shows whether each tenant profile has its required values and which API endpoints and runtime paths are active.",
        )

    def _build_credentials_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Tenant Credentials", padding=8)
        frame.pack(fill="x")

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="x")
        for profile in ("source", "target"):
            tab = ttk.Frame(notebook, style="Panel.TFrame", padding=6)
            notebook.add(tab, text=PROFILE_LABELS[profile])
            for column in range(COMPACT_GRID_COLUMNS):
                tab.columnconfigure(column, weight=1, uniform=f"{profile}-credentials")
            for index, (field_name, label, _required, secret) in enumerate(CREDENTIAL_FIELDS):
                row, column = compact_grid_position(index)
                self._credential_field(tab, profile, field_name, label, secret, row, column)

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(6, 0))
        import_button = ttk.Button(buttons, text="Import Env", command=self.import_credentials_from_env)
        import_button.pack(side="left")
        self._add_tooltip(
            import_button,
            "Fill both tenant forms from matching environment variables without displaying or logging secret values.",
        )
        copy_button = ttk.Button(buttons, text="Copy to Dest", command=self.copy_source_to_destination)
        copy_button.pack(side="left", padx=(6, 0))
        self._add_tooltip(
            copy_button,
            "Copy every Source field into Destination. A later restore would then target that same tenant, so verify this choice carefully.",
        )
        clear_button = ttk.Button(buttons, text="Clear", command=self.clear_credentials)
        clear_button.pack(side="left", padx=(6, 0))
        self._add_tooltip(
            clear_button,
            "Clear the credential forms in memory. This does not edit environment variables or .env files.",
        )
        show_secrets = ttk.Checkbutton(
            buttons,
            text="Show secrets",
            variable=self.show_secrets_var,
            command=self.refresh_secret_visibility,
        )
        show_secrets.pack(side="right")
        self._add_tooltip(
            show_secrets,
            "Temporarily reveal secret fields on screen. Secrets remain excluded from operator and HTTP audit logs.",
        )

    def _build_policy_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Policy Rule Types", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        checks = ttk.Frame(frame, style="Panel.TFrame")
        checks.pack(fill="x")
        for column in range(COMPACT_GRID_COLUMNS):
            checks.columnconfigure(column, weight=1, uniform="policy-types")
        for index, policy_type in enumerate(POLICY_TYPES):
            row, column = compact_grid_position(index)
            check = ttk.Checkbutton(
                checks,
                text=policy_display_name(policy_type),
                variable=self.policy_vars[policy_type],
            )
            check.grid(row=row, column=column, sticky="w", padx=(0, 8), pady=1)
            self._add_tooltip(
                check,
                f"Include {policy_display_name(policy_type)} rules in backup and compare operations.",
            )

        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(6, 0))
        access_button = ttk.Button(buttons, text="Access Only", command=self.select_access_only)
        access_button.pack(side="left")
        self._add_tooltip(access_button, "Select only Access Policy rules for subsequent backup and compare actions.")
        all_button = ttk.Button(buttons, text="All Rule Types", command=self.select_all_policies)
        all_button.pack(side="left", padx=(6, 0))
        self._add_tooltip(all_button, "Select every supported policy rule type for subsequent backup and compare actions.")

    def _build_backup_security_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Backup Security", padding=8)
        frame.pack(fill="x", pady=(0, 8))

        encrypt_check = ttk.Checkbutton(
            frame,
            text="Encrypt backup files",
            variable=self.encrypt_backups_var,
        )
        encrypt_check.pack(anchor="w")
        self._add_tooltip(
            encrypt_check,
            "Store backup JSON as OpenSSL-compatible .json.enc files. Diff, report, result, and audit files remain plaintext.",
        )
        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Passphrase", style="Panel.TLabel", width=14).pack(side="left")
        entry = ttk.Entry(row, textvariable=self.backup_passphrase_var, show="*")
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.secret_entries.append(entry)
        self._add_tooltip(
            entry,
            "Passphrase used to encrypt or decrypt backup files. It is passed through the process environment, not the command line.",
        )

    def _build_artifact_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Workflow Artifacts", padding=8)
        frame.pack(fill="x")

        self._path_row(frame, "Desired backup", self.source_backup_var, "json")
        self._path_row(frame, "Destination backup", self.target_backup_var, "json")
        self._path_row(frame, "Restore diff", self.diff_var, "json")
        self._path_row(frame, "Report", self.report_var, "html")
        self._path_row(frame, "Reviewed simulation", self.simulation_var, "json")
        self._path_row(frame, "Restore result", self.apply_result_var, "json")
        self._path_row(frame, "Audit log", self.audit_log_var, "log")

    def _build_safeguard_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Restore Safeguards", padding=8)
        frame.pack(fill="x")

        safeguards = (
            ("Strict manifest", self.strict_manifest_var),
            ("Allow deletes", self.allow_delete_var),
            ("Allow high-impact", self.allow_high_impact_var),
            ("Allow endpoint-error backups", self.allow_failed_backups_var),
            ("Bypass preflight block", self.ignore_preflight_var),
        )
        for column in range(COMPACT_GRID_COLUMNS):
            frame.columnconfigure(column, weight=1, uniform="restore-safeguards")
        for index, (label, variable) in enumerate(safeguards):
            row, column = compact_grid_position(index)
            check = ttk.Checkbutton(frame, text=label, variable=variable)
            check.grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0, 8),
                pady=1,
            )
            self._add_tooltip(check, SAFEGUARD_TOOLTIPS[label])

    def _build_restore_scope_panel(self, parent: ttk.Frame) -> None:
        selected = ttk.LabelFrame(parent, text="Selective Restore", padding=8)
        selected.pack(fill="x", pady=(0, 8))
        ttk.Label(
            selected,
            text="Canonical object selectors",
            style="Panel.TLabel",
        ).pack(anchor="w")
        selector_entry = ttk.Entry(selected, textvariable=self.restore_selector_var)
        selector_entry.pack(
            fill="x",
            pady=(3, 2),
        )
        self._add_tooltip(
            selector_entry,
            "Enter stable selectors such as servers/server-a or policy_rules/ACCESS_POLICY:rule-name. Use commas for multiple objects.",
        )
        ttk.Label(
            selected,
            text="Separate multiple selectors with commas. Leave empty for a complete restore.",
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).pack(anchor="w")

        resources = ttk.LabelFrame(parent, text="Whole Resource Types", padding=8)
        resources.pack(fill="x", pady=(0, 8))
        for column in range(COMPACT_GRID_COLUMNS):
            resources.columnconfigure(
                column,
                weight=1,
                uniform="restore-resource-types",
            )
        for index, resource_type in enumerate(MIGRATION_ORDER):
            row, column = compact_grid_position(index)
            check = ttk.Checkbutton(
                resources,
                text=resource_display_name(resource_type),
                variable=self.restore_resource_vars[resource_type],
            )
            check.grid(row=row, column=column, sticky="w", padx=(0, 8), pady=1)
            self._add_tooltip(
                check,
                f"Include every changed {resource_display_name(resource_type)} object in the selective restore scope.",
            )

        behavior = ttk.LabelFrame(parent, text="Scope Behavior", padding=8)
        behavior.pack(fill="x")
        behavior.columnconfigure(0, weight=1)
        behavior.columnconfigure(1, weight=1)
        dependency_check = ttk.Checkbutton(
            behavior,
            text="Include writable dependencies",
            variable=self.include_dependencies_var,
        )
        dependency_check.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._add_tooltip(
            dependency_check,
            "Recursively add missing writable dependencies to the restore scope. Read-only or unresolved references still block planning.",
        )
        order_check = ttk.Checkbutton(
            behavior,
            text="Restore policy order",
            variable=self.restore_policy_order_var,
        )
        order_check.grid(row=0, column=1, sticky="w")
        self._add_tooltip(
            order_check,
            "Also apply the desired bulk policy-rule order. Leave off when restoring one rule without changing evaluation order.",
        )
        clear_scope = ttk.Button(
            behavior,
            text="Clear Scope",
            command=self.clear_restore_scope,
        )
        clear_scope.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._add_tooltip(
            clear_scope,
            "Clear all selectors and scope options so the next plan covers the complete restore diff.",
        )

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Run Workflow", padding=8)
        frame.pack(fill="x")

        backup = ttk.LabelFrame(frame, text="1. Create / Compare Backups", padding=6)
        backup.pack(fill="x")
        backup_row_1 = ttk.Frame(backup, style="Panel.TFrame")
        backup_row_1.pack(fill="x")
        self._action_button(backup_row_1, "Backup Source", self.run_backup_source).pack(side="left", fill="x", expand=True)
        self._action_button(backup_row_1, "Backup Destination", self.run_backup_target).pack(side="left", fill="x", expand=True, padx=(6, 0))
        backup_row_2 = ttk.Frame(backup, style="Panel.TFrame")
        backup_row_2.pack(fill="x", pady=(6, 0))
        self._action_button(backup_row_2, "Compare Source to Destination", self.run_plan, style="Primary.TButton").pack(side="left", fill="x", expand=True)

        restore = ttk.LabelFrame(frame, text="2. Restore Destination", padding=6)
        restore.pack(fill="x", pady=(6, 0))
        restore_row_1 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_1.pack(fill="x")
        self._action_button(restore_row_1, "Choose Desired Backup", self.choose_desired_backup).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_1, "Build Restore Plan", self.run_restore_plan, style="Primary.TButton").pack(side="left", fill="x", expand=True, padx=(6, 0))
        restore_row_2 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_2.pack(fill="x", pady=(6, 0))
        self._action_button(restore_row_2, "Validate", self.run_validate).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_2, "Preflight", self.run_preflight).pack(side="left", fill="x", expand=True, padx=(6, 0))
        restore_row_3 = ttk.Frame(restore, style="Panel.TFrame")
        restore_row_3.pack(fill="x", pady=(6, 0))
        self._action_button(restore_row_3, "Simulate", self.run_restore_dry).pack(side="left", fill="x", expand=True)
        self._action_button(restore_row_3, "Restore", self.run_restore, style="Danger.TButton").pack(side="left", fill="x", expand=True, padx=(6, 0))

        operations = ttk.LabelFrame(frame, text="3. Inventory / Audit", padding=6)
        operations.pack(fill="x", pady=(6, 0))
        operations_row_1 = ttk.Frame(operations, style="Panel.TFrame")
        operations_row_1.pack(fill="x")
        self._action_button(operations_row_1, "Snapshots", self.run_snapshot_list).pack(side="left", fill="x", expand=True)
        self._action_button(operations_row_1, "Latest Inventory", self.run_inventory_list).pack(side="left", fill="x", expand=True, padx=(6, 0))
        operations_row_2 = ttk.Frame(operations, style="Panel.TFrame")
        operations_row_2.pack(fill="x", pady=(6, 0))
        self._action_button(operations_row_2, "Audit Summary", self.run_audit_summary).pack(side="left", fill="x", expand=True)
        self._action_button(operations_row_2, "Verify Ledger", self.run_audit_verify).pack(side="left", fill="x", expand=True, padx=(6, 0))

        utilities = ttk.LabelFrame(frame, text="4. Review", padding=6)
        utilities.pack(fill="x", pady=(6, 0))
        utility_row = ttk.Frame(utilities, style="Panel.TFrame")
        utility_row.pack(fill="x")
        self._action_button(utility_row, "Report", self.run_report).pack(side="left", fill="x", expand=True)
        self._action_button(utility_row, "Coverage", self.run_coverage).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_activity_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Activity", padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.detail_var, style="Panel.TLabel").pack(side="left", fill="x", expand=True)
        self.stop_button = ttk.Button(top, text="Stop", command=self.stop_command, state="disabled")
        self.stop_button.pack(side="right", padx=(8, 0))
        self._add_tooltip(
            self.stop_button,
            "Request termination of the running command. Review its output and artifacts before starting another operation.",
        )
        open_log = ttk.Button(top, text="Open Log", command=self.open_audit_log)
        open_log.pack(side="right", padx=(8, 0))
        self._add_tooltip(
            open_log,
            "Open the currently selected detailed HTTP audit log in the system default application.",
        )
        open_report = ttk.Button(top, text="Open Report", command=self.open_report)
        open_report.pack(side="right")
        self._add_tooltip(
            open_report,
            "Open the currently selected HTML report in the system default browser.",
        )

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
        self._add_tooltip(
            self.log,
            "Live command output. Generated artifact paths are captured automatically in the Artifacts tab.",
        )

    def _path_row(self, parent: ttk.Frame, label: str, var: tk.StringVar, kind: str) -> None:
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=3)
        label_widget = ttk.Label(row, text=label, style="Panel.TLabel", width=18)
        label_widget.pack(side="left")
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 6))
        command = self._save_file if label == "Report" else self._open_file
        browse = ttk.Button(row, text="Browse", command=lambda: command(var, kind))
        browse.pack(side="right")
        tooltip = ARTIFACT_TOOLTIPS[label]
        self._add_tooltip(label_widget, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(
            browse,
            f"{'Choose where to save' if label == 'Report' else 'Select'} the {label.casefold()} file.",
        )

    def _credential_field(
        self,
        parent: ttk.Frame,
        profile: str,
        field_name: str,
        label: str,
        secret: bool,
        row: int,
        column: int,
    ) -> None:
        cell = ttk.Frame(parent, style="Panel.TFrame")
        cell.grid(row=row, column=column, sticky="ew", padx=(0, 6), pady=2)
        label_widget = ttk.Label(cell, text=label, style="Panel.TLabel")
        label_widget.pack(anchor="w")
        if field_name == "AUTH_MODE":
            entry = ttk.Combobox(
                cell,
                textvariable=self.credential_vars[profile][field_name],
                values=("legacy", "oneapi"),
                state="readonly",
            )
        else:
            entry = ttk.Entry(
                cell,
                textvariable=self.credential_vars[profile][field_name],
                show="*" if secret and not self.show_secrets_var.get() else "",
            )
        entry.pack(fill="x", pady=(2, 0))
        tooltip = CREDENTIAL_TOOLTIPS[field_name]
        self._add_tooltip(label_widget, tooltip)
        self._add_tooltip(entry, tooltip)
        if secret:
            self.secret_entries.append(entry)

    def _action_button(self, parent: ttk.Frame, text: str, command, style: str = "TButton") -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style=style)
        self.command_buttons.append(button)
        self._add_tooltip(button, ACTION_TOOLTIPS[text])
        return button

    def _add_tooltip(self, widget: tk.Misc, text: str | TooltipProvider) -> None:
        self.tooltips.append(ToolTip(widget, text))

    def _add_notebook_tooltips(
        self,
        notebook: ttk.Notebook,
        descriptions: dict[str, str],
    ) -> None:
        def description_at_pointer(event: tk.Event) -> str | None:
            try:
                index = notebook.index(f"@{event.x},{event.y}")
                tab_name = str(notebook.tab(index, "text"))
            except tk.TclError:
                return None
            return descriptions.get(tab_name)

        self._add_tooltip(notebook, description_at_pointer)

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

    def encryption_args(self) -> list[str]:
        return build_encryption_args(self.encrypt_backups_var.get())

    def selected_restore_resource_types(self) -> list[str]:
        return [
            resource_type
            for resource_type, variable in self.restore_resource_vars.items()
            if variable.get()
        ]

    def restore_selection_args(self) -> list[str] | None:
        try:
            return build_restore_selection_args(
                self.restore_selector_var.get(),
                self.selected_restore_resource_types(),
                include_dependencies=self.include_dependencies_var.get(),
                restore_policy_order=self.restore_policy_order_var.get(),
            )
        except ValueError as error:
            self._show_error(str(error))
            return None

    def clear_restore_scope(self) -> None:
        self.restore_selector_var.set("")
        self.include_dependencies_var.set(False)
        self.restore_policy_order_var.set(False)
        for variable in self.restore_resource_vars.values():
            variable.set(False)
        self.detail_var.set("Restore scope cleared; complete restore selected")

    def global_args(self) -> list[str]:
        return [*self.encryption_args(), *self.policy_args()]

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
        self._run_command("Backup Source", self.global_args() + ["backup", "source"])

    def run_backup_target(self) -> None:
        if not self.ensure_policy_scope():
            return
        if not self._require_profiles("backup destination", ("target",)):
            return
        self._run_command("Backup Destination", self.global_args() + ["backup", "target"])

    def choose_desired_backup(self) -> None:
        self._open_file(self.source_backup_var, "json")

    def run_plan(self) -> None:
        if not self.ensure_policy_scope():
            return
        if not self._require_profiles("plan", ("source", "target")):
            return
        selection_args = self.restore_selection_args()
        if selection_args is None:
            return
        self.simulation_var.set("")
        self._run_command(
            "Compare Source to Destination",
            self.global_args() + ["plan", *selection_args],
        )

    def run_restore_plan(self) -> None:
        source_backup = self.source_backup_var.get().strip()
        if not source_backup:
            self._show_error("Select the desired backup snapshot first.")
            return
        if not self._require_profiles("restore from backup", ("target",)):
            return
        selection_args = self.restore_selection_args()
        if selection_args is None:
            return
        self.simulation_var.set("")
        args = [
            *self.global_args(),
            "restore-plan",
            "--source-backup",
            source_backup,
            *selection_args,
        ]
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
        paths = self._restore_paths()
        if not paths:
            return
        self._run_command("Simulate Restore", self._restore_args(paths, dry_run=True))

    def run_restore(self) -> None:
        if not self._require_profiles("restore", ("target",)):
            return
        paths = self._restore_paths()
        if not paths:
            return
        simulation = self.simulation_var.get().strip()
        if not simulation:
            self._show_error("Run or select a reviewed simulation before restoring.")
            return
        if not messagebox.askyesno(
            "Confirm Restore",
            "Verify the reviewed simulation, capture a fresh destination backup, and restore with --yes?",
        ):
            return
        self._run_command("Restore", self._restore_args(paths, dry_run=False))

    def run_snapshot_list(self) -> None:
        self._run_command("Snapshot Catalog", ["snapshot", "list"])

    def run_inventory_list(self) -> None:
        self._run_command(
            "Latest Inventory",
            [
                "inventory",
                "list",
                "--snapshot",
                "latest",
                "--restore-commands",
            ],
        )

    def run_audit_summary(self) -> None:
        self._run_command("Audit Summary", ["audit", "summary"])

    def run_audit_verify(self) -> None:
        self._run_command("Verify Audit Ledger", ["audit", "verify"])

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
            "simulate" if dry_run else "restore",
            "--source-backup",
            paths["source_backup"],
            "--target-backup",
            paths["target_backup"],
            "--diff",
            paths["diff"],
        ]
        if not dry_run:
            args.extend(["--simulation", self.simulation_var.get().strip(), "--yes"])
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
        backup_passphrase = self.backup_passphrase_var.get()
        if backup_passphrase:
            run_env[BACKUP_PASSPHRASE_ENV] = backup_passphrase
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
        self._open_existing_path(report, "Report")

    def open_audit_log(self) -> None:
        audit_log = self.audit_log_var.get().strip()
        if not audit_log:
            self._show_error("No audit log file is selected.")
            return
        self._open_existing_path(audit_log, "Audit log")

    def _open_existing_path(self, value: str, label: str) -> None:
        path = Path(value)
        if not path.is_absolute():
            path = WORK_DIR / path
        if not path.exists():
            self._show_error(f"{label} file does not exist: {path}")
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
            "simulation": self.simulation_var,
            "apply_result": self.apply_result_var,
            "audit_log": self.audit_log_var,
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
        if kind == "log":
            return [("Log files", "*.log"), ("All files", "*.*")]
        return [("JSON and encrypted files", ("*.json", "*.json.enc", "*.enc")), ("All files", "*.*")]

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
