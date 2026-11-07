"""Sightware GUI — Logs tab (tails the rotating .valtix logs, secrets redacted)."""
from __future__ import annotations

import os
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from ..theme import BG, BG_RAISED, CARD, LOSS, TEXT, TEXT_DIM, TEXT_FAINT

MAX_LINES = 500


class LogsTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.log_dir = (os.environ.get("SIGHTWARE_LOG_DIR")
                        or Path(__file__).resolve().parents[2] / ".valtix")
        self.log_dir = Path(self.log_dir)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(top, text="LOG FILE", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.file_var = tk.StringVar()
        self.file_cb = ttk.Combobox(top, textvariable=self.file_var,
                                    state="readonly", width=26)
        self.file_cb.pack(side="left", padx=(8, 6))
        self.file_cb.bind("<<ComboboxSelected>>", lambda e: self._load())
        ttk.Button(top, text="⟳", style="Ghost.TButton", width=3,
                   command=self._load).pack(side="left", padx=2)
        ttk.Button(top, text="Open folder", style="Ghost.TButton",
                   command=self._open_folder).pack(side="left", padx=8)
        self.status_lbl = tk.Label(top, text="", bg=BG, fg=TEXT_FAINT,
                                   font=("Segoe UI", 8))
        self.status_lbl.pack(side="left", padx=8)

        wrap = tk.Frame(self, bg=CARD, highlightbackground="#26343F",
                        highlightthickness=1)
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.text = tk.Text(wrap, bg="#0B141C", fg=TEXT, insertbackground=TEXT,
                            font=("Consolas", 9), wrap="none", bd=0,
                            state="disabled", padx=10, pady=8)
        ybar = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        xbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        self.text.pack(fill="both", expand=True)
        for kind in ("info", "warning", "error"):
            self.text.tag_configure(kind, foreground={
                "info": TEXT_DIM, "warning": "#F5C542", "error": LOSS}[kind])

    def on_show(self) -> None:
        files = self._log_files()
        names = [f.name for f in files]
        self.file_cb.configure(values=names or ["(no logs yet)"])
        if names and (not self.file_var.get() or self.file_var.get() not in names):
            self.file_var.set(names[0])
        elif not names:
            self.file_var.set("(no logs yet)")
        self._load()

    def _log_files(self) -> list[Path]:
        if not self.log_dir.is_dir():
            return []

        def _mtime(p: Path) -> float:
            # a rotating log can vanish between glob and stat
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0
        return sorted(self.log_dir.glob("*.log"), key=_mtime, reverse=True)

    def _load(self) -> None:
        name = self.file_var.get()
        path = self.log_dir / name if name and not name.startswith("(") else None
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if not path or not path.is_file():
            self.text.insert("end", "No log file selected.\n", "info")
            self.text.configure(state="disabled")
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="replace") \
                .splitlines()[-MAX_LINES:]
            size_kb = path.stat().st_size / 1024
            self.status_lbl.configure(
                text=f"last {len(lines)} lines · {size_kb:.0f} KB · {path.name}")
            for line in lines:
                kind = "error" if " ERROR " in line else \
                       "warning" if " WARNING " in line else "info"
                self.text.insert("end", line + "\n", kind)
        except OSError as e:
            self.text.insert("end", f"Could not read {path}: {e}\n", "error")
        self.text.see("end")
        self.text.configure(state="disabled")

    def _open_folder(self) -> None:
        try:
            os.startfile(str(self.log_dir))  # noqa: S606 (windows-only app)
        except (OSError, AttributeError):
            self.app.toast.show(f"Log folder: {self.log_dir}", kind="info")
