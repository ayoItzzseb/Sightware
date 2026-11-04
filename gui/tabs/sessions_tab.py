"""Sightware GUI — Sessions tab (session tracker with goals)."""
from __future__ import annotations

import time

import tkinter as tk
from tkinter import ttk

from ..theme import (BG, CARD, LINE, TEAL, TEXT, TEXT_DIM, TEXT_FAINT, WIN,
                   LOSS, RED)
from ..widgets import (DataTable, Column, ScrollFrame, StatCard, section_title)

GOAL_TYPES = ["none", "rr", "rank", "matches", "stopLoss"]
GOAL_LABELS = {
    "rr": "Reach an RR target (e.g. +100 RR)",
    "rank": "Reach a rank (e.g. Diamond 2)",
    "matches": "Play a number of ranked matches",
    "stopLoss": "Stop after losing this much RR",
}


def _ts(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except (TypeError, ValueError, OSError):
        return "—"


class SessionsTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.core = app.core
        self._loaded_once = False
        self._archive: list[dict] = []
        self._selected: str | None = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 4))
        ttk.Button(top, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.refresh).pack(side="left")
        self.start_btn = ttk.Button(top, text="▶ Start session", style="Success.TButton",
                                    command=self._start_dialog)
        self.start_btn.pack(side="left", padx=8)
        self.end_btn = ttk.Button(top, text="■ End session", style="Accent.TButton",
                                  command=self._end_session)
        self.end_btn.pack(side="left", padx=2)
        self.del_btn = ttk.Button(top, text="Delete selected", style="Danger.TButton",
                                  command=self._delete_selected, state="disabled")
        self.del_btn.pack(side="right")

        # active session card
        self.active_card = tk.Frame(self, bg=CARD, highlightbackground=LINE,
                                    highlightthickness=1, padx=16, pady=12)
        self.active_card.pack(fill="x", padx=16, pady=(8, 4))
        self.active_title = tk.Label(self.active_card, text="NO ACTIVE SESSION",
                                     bg=CARD, fg=TEXT_FAINT,
                                     font=("Segoe UI", 9, "bold"))
        self.active_title.pack(anchor="w")
        self.active_info = tk.Label(self.active_card, text="Start a session to "
                                    "track this play block against a goal.",
                                    bg=CARD, fg=TEXT_DIM, font=("Segoe UI", 9))
        self.active_info.pack(anchor="w", pady=(2, 6))
        self.active_stats = tk.Frame(self.active_card, bg=CARD)
        self.active_stats.pack(fill="x")
        self.s_matches = StatCard(self.active_stats, "matches")
        self.s_wl = StatCard(self.active_stats, "w – l")
        self.s_wr = StatCard(self.active_stats, "win rate")
        self.s_net = StatCard(self.active_stats, "net rr")
        for c in (self.s_matches, self.s_wl, self.s_wr, self.s_net):
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner
        section_title(body, "session archive").pack(anchor="w", padx=16, pady=(10, 4))
        self.table = DataTable(body, [
            Column("started", "Started", 130),
            Column("ended", "Ended", 130),
            Column("goal", "Goal", 200, stretch=True),
            Column("matches", "Matches", 66, "e"),
            Column("wl", "W–L", 60, "e"),
            Column("winRate", "WR%", 54, "e"),
            Column("net", "Net RR", 64, "e"),
            Column("outcome", "Outcome", 96),
        ], height=320, row_h=26, on_row_click=self._select_row)
        self.table.pack(fill="x", padx=16, pady=(0, 12))

    def on_show(self) -> None:
        if not self._loaded_once:
            self.refresh()

    def refresh(self) -> None:
        def work():
            return self.core.sessions()
        self.app.run_bg(work, self._apply, self._error)

    def _error(self, err: str) -> None:
        self.active_info.configure(text=f"Failed to load sessions: "
                                        f"{err.splitlines()[-1]}", fg=LOSS)

    def _apply(self, payload: dict) -> None:
        self._loaded_once = True
        active = payload.get("active")
        archive = payload.get("archive") or []
        self._archive = archive
        self._render_active(active)
        self._render_archive(archive)

    def _render_active(self, active: dict | None) -> None:
        if active:
            s = active.get("summary") or {}
            goal = active.get("goal") or {}
            goal_txt = self._goal_text(goal) or "no goal set"
            started = _ts(active.get("startedAt"))
            self.active_title.configure(
                text=f"ACTIVE SESSION — started {started}", fg=TEAL)
            self.active_info.configure(
                text=f"Goal: {goal_txt}" + (
                    f" · {s.get('matches', 0)} matches so far" if s.get("matches") else ""),
                fg=TEXT_DIM)
            self.s_matches.set(str(s.get("matches", 0)))
            self.s_wl.set(f"{s.get('wins', 0)} – {s.get('losses', 0)}")
            self.s_wr.set(f"{s.get('winRate')}%" if s.get("winRate") is not None else "—")
            net = s.get("net", 0)
            self.s_net.set(f"{'+' if net > 0 else ''}{net}",
                           color=WIN if net > 0 else LOSS if net < 0 else TEXT)
            for c in (self.s_matches, self.s_wl, self.s_wr, self.s_net):
                c.pack_configure(side="left", padx=(0, 8), fill="x", expand=True)
        else:
            self.active_title.configure(text="NO ACTIVE SESSION", fg=TEXT_FAINT)
            self.active_info.configure(
                text="Start a session to track this play block against a goal.",
                fg=TEXT_DIM)
            self.s_matches.set("—")
            self.s_wl.set("—")
            self.s_wr.set("—")
            self.s_net.set("—")

    @staticmethod
    def _goal_text(goal: dict | None) -> str:
        if not goal:
            return ""
        kind = goal.get("type")
        target = goal.get("target")
        if kind == "rr":
            return f"reach {target:+} RR"
        if kind == "rank":
            return f"reach {target}"
        if kind == "matches":
            return f"play {target} matches"
        if kind == "stopLoss":
            return f"stop at −{target} RR"
        return ""

    def _render_archive(self, archive: list[dict]) -> None:
        rows = []
        for s in archive:
            summary = s.get("summary") or {}
            net = summary.get("net", 0)
            rows.append({
                "cells": {
                    "started": _ts(s.get("startedAt")),
                    "ended": _ts(s.get("endedAt")),
                    "goal": self._goal_text(s.get("goal")) or "—",
                    "matches": str(summary.get("matches", 0)),
                    "wl": f"{summary.get('wins', 0)}–{summary.get('losses', 0)}",
                    "winRate": (f"{summary.get('winRate')}%"
                                if summary.get("winRate") is not None else "—"),
                    "net": f"{'+' if net > 0 else ''}{net}",
                    "outcome": (s.get("outcome") or "").title() or "—",
                },
                "colors": {
                    "net": WIN if net > 0 else LOSS if net < 0 else TEXT_DIM,
                },
                "data": {"id": s.get("id")},
            })
        self.table.set_rows(rows)

    def _select_row(self, data: dict) -> None:
        self._selected = data.get("id")
        self.del_btn.configure(state="normal" if self._selected else "disabled")

    def _start_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Start session")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.geometry("420x250")
        tk.Label(dlg, text="SESSION GOAL", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18,
                                                    pady=(18, 6))
        kind_var = tk.StringVar(value="none")
        kind_cb = ttk.Combobox(dlg, textvariable=kind_var, state="readonly",
                               values=GOAL_TYPES, width=16)
        kind_cb.pack(anchor="w", padx=18)
        target_var = tk.StringVar()
        target_entry = ttk.Entry(dlg, textvariable=target_var, width=20)
        target_entry.pack(anchor="w", padx=18, pady=(8, 2))

        def on_kind(_e=None):
            kind = kind_var.get()
            if kind in GOAL_LABELS:
                target_entry.configure(state="normal")
            if kind == "none":
                target_entry.configure(state="disabled")
        kind_cb.bind("<<ComboboxSelected>>", on_kind)
        on_kind()

        def confirm():
            kind = kind_var.get()
            goal = None
            if kind != "none":
                goal = {"type": kind, "target": target_var.get()}
            dlg.destroy()

            def work():
                return self.core.session_start(goal)
            self.app.run_bg(work, lambda _r: (self.app.toast.show(
                "Session started", kind="ok"), self.refresh()))

        ttk.Button(dlg, text="Start session", style="Accent.TButton",
                   command=confirm).pack(side="right", padx=18, pady=16)

    def _end_session(self) -> None:
        def work():
            return self.core.session_end()
        self.app.run_bg(work, lambda r: (self.app.toast.show(
            "Session ended", kind="ok"), self.refresh()))

    def _delete_selected(self) -> None:
        if not self._selected:
            return
        sid = self._selected
        self._selected = None
        self.del_btn.configure(state="disabled")

        def work():
            return self.core.session_delete(sid)
        self.app.run_bg(work, lambda _r: self.refresh())
