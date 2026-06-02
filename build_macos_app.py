#!/usr/bin/env python3
"""Build a lightweight macOS .app wrapper for ZPA-Backup and Restore."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path


APP_NAME = "ZPA-Backup and Restore"
BUNDLE_ID = "de.zslab.zpa-backup-restore"
EXECUTABLE_NAME = "zpa-backup-restore"
VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
APP_PATH = DIST_DIR / f"{APP_NAME}.app"
CONTENTS_DIR = APP_PATH / "Contents"
MACOS_DIR = CONTENTS_DIR / "MacOS"
RESOURCES_DIR = CONTENTS_DIR / "Resources"
LEGACY_APP_PATHS = [
    DIST_DIR / "ZPA Cloner.app",
]

RUNTIME_FILES = [
    "zpa_cloner_app.py",
    "zpa_cloner.py",
    "zpa_policy_tool.py",
    "zpa_resources.py",
    "zpa_integrity.py",
    "zpa_report.py",
    ".env.example",
    "README.md",
    "ZPA_API_COVERAGE_AUDIT.md",
]


def write_info_plist() -> None:
    info = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>{APP_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>{EXECUTABLE_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>{BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>{APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>{VERSION}</string>
  <key>CFBundleVersion</key>
  <string>{VERSION}</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
"""
    (CONTENTS_DIR / "Info.plist").write_text(info, encoding="utf-8")


def write_launcher() -> None:
    launcher = """#!/bin/sh
APP_CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES="$APP_CONTENTS/Resources"
export PYTHONPATH="$RESOURCES${PYTHONPATH:+:$PYTHONPATH}"

for candidate in "${ZPA_BACKUP_RESTORE_PYTHON:-}" "${ZPA_CLONER_PYTHON:-}" /opt/homebrew/bin/python3 /usr/local/bin/python3 /opt/homebrew/opt/python@3.14/bin/python3.14 /usr/bin/python3
do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    "$candidate" -c "import tkinter" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
      exec "$candidate" "$RESOURCES/zpa_cloner_app.py" "$@"
    fi
  fi
done

osascript -e 'display dialog "ZPA-Backup and Restore needs Python 3 with Tkinter. Install Python 3 from Homebrew or python.org, then reopen the app." buttons {"OK"} default button "OK" with icon caution'
exit 1
"""
    launcher_path = MACOS_DIR / EXECUTABLE_NAME
    launcher_path.write_text(launcher, encoding="utf-8")
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_runtime_files() -> None:
    for file_name in RUNTIME_FILES:
        source = ROOT / file_name
        if not source.exists():
            raise FileNotFoundError(source)
        shutil.copy2(source, RESOURCES_DIR / file_name)


def build() -> Path:
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    for legacy_path in LEGACY_APP_PATHS:
        if legacy_path.exists() and legacy_path != APP_PATH:
            shutil.rmtree(legacy_path)
    MACOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    copy_runtime_files()
    write_info_plist()
    write_launcher()
    (CONTENTS_DIR / "PkgInfo").write_text("APPL????", encoding="utf-8")
    return APP_PATH


def main() -> int:
    app_path = build()
    print(f"Built {app_path}")
    print("Runtime data folder: ~/Documents/ZPA-Backup and Restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
