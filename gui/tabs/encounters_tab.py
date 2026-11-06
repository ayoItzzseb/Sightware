"""Sightware GUI — Encounters tab (local smurf radar / encounter log)."""
from __future__ import annotations

import time

import tkinter as tk
from tkinter import ttk

from ..theme import (AMBER, BG, BG_RAISED, CARD, ORANGE, RED, TEAL, TEXT,
                   TEXT_DIM, TEXT_FAINT, WIN, LOSS)
from ..widgets import (DataTable, Column, ScrollFrame, StatCard, section_title)


def _notes_file():
    import os
    base = os.environ.get("VALTIX_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "backend", "data")
    return os.path.join(base, "encounter-notes.json")


def _load_notes():
    import json
    try:
        with open(_notes_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_notes(notes):
    import json, os
    os.makedirs(os.path.dirname(_notes_file()), exist_ok=True)
    with open(_notes_file(), "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)

from ..dialogs import PlayerProfileDialog


def _ago(ts) -> str:
    try:
        d = time.time() - int(ts)
    except (TypeError, ValueError):
        return "—"
    if d < 3600:
        return f"{max(1, round(d / 60))}m ago"
    if d < 86400:
        return f"{round(d / 3600)}h ago"
    return f"{round(d / 86400)}d ago"


class EncountersTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.core = app.core
        self._loaded_once = False
        self._scope = "current"

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 4))
        self.scope_var = tk.StringVar(value="This account")
        cb = ttk.Combobox(top, textvariable=self.scope_var, state="readonly",
                          width=18, values=["This account", "All saved accounts"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._on_scope)
        ttk.Button(top, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.refresh).pack(side="left", padx=8)
        self.meta_lbl = tk.Label(top, text="", bg=BG, fg=TEXT_FAINT,
                                 font=("Segoe UI", 8))
        self.meta_lbl.pack(side="left", padx=8)

        self.cards = tk.Frame(self, bg=BG)
        self.cards.pack(fill="x", padx=16, pady=(8, 4))
        self.c_players = StatCard(self.cards, "tracked players")
        self.c_allies = StatCard(self.cards, "played with")
        self.c_enemies = StatCard(self.cards, "played against")
        self.c_accounts = StatCard(self.cards, "accounts in log")
        for c in (self.c_players, self.c_allies, self.c_enemies, self.c_accounts):
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner

        section_title(body, "encounter log").pack(anchor="w", padx=16, pady=(8, 4))
        tk.Label(body, text="players seen in your lobbies (≥ 2 games) · click a row "
                 "for their profile · names that Riot hides stay hidden",
                 bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(anchor="w", padx=18)
        self.table = DataTable(body, [
            Column("name", "Player", 190, stretch=True),
            Column("agent", "Top agent", 100),
            Column("with", "With", 70, "e"),
            Column("withWl", "W–L with", 76, "e"),
            Column("against", "Against", 72, "e"),
            Column("againstWl", "W–L vs", 70, "e"),
            Column("withKd", "K/D w", 54, "e"),
            Column("withHs", "HS% w", 56, "e"),
            Column("rank", "Rank", 112),
            Column("peak", "Peak", 104),
            Column("level", "Lvl", 48, "e"),
            Column("seen", "Last seen", 82, "e"),
            Column("note", "Note", 150, stretch=True),
        ], height=430, row_h=27, on_row_click=self._open_player)
        tbl_btns = tk.Frame(body, bg=BG)
        tbl_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(tbl_btns, text="Edit note on selected", style="Ghost.TButton",
                   command=self._edit_note).pack(side="left")
        ttk.Button(tbl_btns, text="Export CSV", style="Ghost.TButton",
                   command=self._export_csv).pack(side="left", padx=6)
        self.table.pack(fill="x", padx=16, pady=(4, 12))

        self.loading = tk.Label(body, text="", bg=BG, fg=TEXT_DIM,
                                font=("Segoe UI", 9))
        self.loading.pack(padx=16, anchor="w")

    def on_show(self) -> None:
        if not self._loaded_once:
            self.refresh()

    def _on_scope(self, _evt=None) -> None:
        self._scope = ("all" if self.scope_var.get() == "All saved accounts"
                       else "current")
        self.refresh()

    def refresh(self) -> None:
        scope = self._scope

        def work():
            return self.core.encounters(scope=scope)

        self.loading.configure(text="Loading encounters…", fg=TEXT_DIM)
        self.app.run_bg(work, self._apply, self._error)

    def _error(self, err: str) -> None:
        self.loading.configure(text=f"Failed: {err.splitlines()[-1]}", fg=LOSS)

    def _apply(self, payload: dict) -> None:
        self._loaded_once = True
        players = payload.get("players") or []
        with_games = sum(1 for p in players if (p.get("withCount") or 0) >= 2)
        against_games = sum(1 for p in players if (p.get("againstCount") or 0) >= 2)
        self.c_players.set(str(len(players)))
        self.c_allies.set(str(with_games))
        self.c_enemies.set(str(against_games))
        self.c_accounts.set(str(payload.get("accountCount", 1)))
        self.meta_lbl.configure(
            text=("refreshing in background…" if payload.get("refreshing")
                  else f"scope: {payload.get('scope', self._scope)}"))

        notes = _load_notes()
        rows = []
        for p in players:
            with_n = p.get("withCount") or 0
            against_n = p.get("againstCount") or 0
            wr = p.get("winRate")
            rows.append({
                "cells": {
                    "name": p.get("name") or "—",
                    "note": notes.get(
                        (p.get("puuid") or p.get("name") or "").lower(), ""),
                    "agent": p.get("topAgent") or "—",
                    "with": str(with_n) if with_n else "",
                    "withWl": (f"{p.get('winsWith', 0)}–{p.get('lossesWith', 0)}"
                               if with_n else ""),
                    "against": str(against_n) if against_n else "",
                    "againstWl": (f"{p.get('winsAgainst', 0)}–{p.get('lossesAgainst', 0)}"
                                  if against_n else ""),
                    "withKd": str(p.get("withKd")) if p.get("withKd") is not None else "—",
                    "withHs": (f"{p.get('withHsPct')}%"
                               if p.get("withHsPct") is not None else "—"),
                    "rank": p.get("rank") or "—",
                    "peak": p.get("peakRank") or "—",
                    "level": str(p.get("level") or "—"),
                    "seen": _ago(p.get("lastSeen")),
                },
                "colors": {
                    "agent": p.get("topAgentColor") or TEXT_DIM,
                    "rank": p.get("rankColor") or TEXT,
                    "peak": p.get("peakColor") or TEXT_DIM,
                    "withWl": WIN if (p.get("winsWith") or 0) >= (p.get("lossesWith") or 0)
                              else TEXT_DIM,
                    "againstWl": WIN if (p.get("winsAgainst") or 0) >= (p.get("lossesAgainst") or 0)
                                 else TEXT_DIM,
                },
                "data": {"puuid": p.get("puuid"), "name": p.get("name")},
            })
        self.table.set_rows(rows)
        self._players = players
        if not players:
            self.loading.configure(
                text="No encounters recorded yet — they build up while you play "
                     "with Local history enabled.", fg=TEXT_DIM)
        else:
            self.loading.configure(text="", fg=TEXT_DIM)

    def _open_player(self, data: dict) -> None:
        if data.get("puuid"):
            PlayerProfileDialog(self.app, data["puuid"], data.get("name"))

    # ── notes + csv ────────────────────────────────────────────
    def _selected_player(self):
        rows = self.table.rows()
        idx = getattr(self.table, "_sel", None)
        if idx is None or not (0 <= idx < len(rows)):
            return None
        return rows[idx]

    def _edit_note(self):
        row = self._selected_player()
        if not row:
            self.app.toast.show("Select a player row first.", kind="warn")
            return
        data = row.get("data") or {}
        name = (row.get("cells") or {}).get("name") or data.get("name") or ""
        notes = _load_notes()
        key = (data.get("puuid") or name).lower()
        current = notes.get(key, "")
        dlg = tk.Toplevel(self)
        dlg.title(f"Note - {name}")
        dlg.configure(bg=BG)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        txt = tk.Text(dlg, width=44, height=5, bg=BG_RAISED, fg=TEXT,
                      insertbackground=RED, bd=0, font=("Segoe UI", 9))
        txt.pack(padx=14, pady=(14, 8))
        txt.insert("1.0", current)

        def save(_e=None):
            notes[key] = txt.get("1.0", "end").strip()
            _save_notes(notes)
            dlg.destroy()
            self.refresh()
        ttk.Button(dlg, text="Save note", style="Accent.TButton",
                   command=save).pack(pady=(0, 14))
        txt.focus_set()

    def _export_csv(self):
        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(
            title="Export encounters as CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        import csv as csvmod
        notes = _load_notes()
        players = getattr(self, "_players", []) or []
        rows = []
        for p in players:
            key = (p.get("puuid") or p.get("name") or "").lower()
            rows.append({
                "name": p.get("name") or "",
                "agent": p.get("topAgent") or p.get("agent") or "",
                "withGames": p.get("withCount") or 0,
                "withWl": f"{p.get('winsWith', 0)}-{p.get('lossesWith', 0)}",
                "againstGames": p.get("againstCount") or 0,
                "rank": p.get("rank") or "",
                "lastSeen": p.get("lastSeen") or "",
                "note": notes.get(key, ""),
            })
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csvmod.DictWriter(f, fieldnames=list(rows[0].keys()) if rows
                                  else ["name"])
            w.writeheader()
            w.writerows(rows)
        self.app.toast.show(f"Exported {len(rows)} encounters to CSV.", kind="ok")
