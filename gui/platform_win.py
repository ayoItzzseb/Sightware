"""Sightware GUI — Windows integration helpers (startup shortcut)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTUP_BAT = "Sightware (GUI).bat"


def startup_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / \
        "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def start_with_windows_enabled() -> bool:
    return (startup_dir() / STARTUP_BAT).is_file()


def set_start_with_windows(enabled: bool) -> str:
    """Create or remove the Startup-folder launcher. Returns a status message."""
    target = startup_dir() / STARTUP_BAT
    try:
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                cmd = f'start "" pythonw "{ROOT / "run.py"}"'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("@echo off\r\n" + cmd + "\r\n",
                              encoding="utf-8")
            return f"Will start with Windows ({target.name})."
        target.unlink(missing_ok=True)
        return "Removed from Windows startup."
    except OSError as e:
        return f"Startup shortcut failed: {e}"
