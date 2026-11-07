"""Sightware GUI — dialogs: settings, match report, player profile, privacy."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from .theme import (AMBER, BG, BG_RAISED, CARD, LINE, LOSS, ORANGE, PURPLE, RED,
                   readable, RED_SOFT, TEAL, TEXT, TEXT_DIM, TEXT_FAINT, WIN, mix)
from .widgets import (DataTable, Column, ScrollFrame, Switch, section_head,
                     section_title)

from agents import AGENTS
from vconstants import MAPS

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DATA_DIR = Path(os.environ.get("VALTIX_DATA_DIR")
               or BACKEND_DIR / "data")

# Ported verbatim from the v2.5.8 dashboard (SETTING_DEFS) with the
# web-era keys (openDashboardOnLaunch / hideTerminalOnLaunch /
# dashboardEnabled) replaced by their GUI-edition equivalents.
SETTING_DEFS = [
    {"grp": "Assistant", "key": "assistantEnabled",
     "t": "Agent-select assistant",
     "d": "Shows your preferred pick and a recommendation while agent select "
          "is open. Read-only — it never selects anything."},
    {"key": "assistantAutoStart", "t": "Start automatically with VALORANT",
     "d": "The assistant runs whenever Sightware is running and VALORANT is open."},
    {"key": "rememberAgent", "t": "Remember my preferred agent",
     "d": "Persists the agent you last locked as your default pick."},
    {"key": "lowImpactInGame", "t": "Game Mode (reduce background work in game)",
     "d": "While you're in a match, slows background polling to keep FPS "
          "and ping as clean as possible. The Live Board updates slightly "
          "less often — everything else is unaffected."},
    {"grp": "Data & privacy", "key": "localHistoryEnabled", "t": "Local history",
     "d": "Encounter log, RR history and session tracking stored in "
          "backend/data/. Turning it off stops all recording."},
    {"key": "includeLiveStats", "t": "Recent-form stats",
     "d": "Fetches last-5-match K/D, HS% and win-rate for players once a match "
          "has started."},
    {"key": "loadArt", "t": "Game art from valorant-api.com",
     "d": "Agent portraits and rank icons load from the public community CDN "
          "(GET only, no personal data). Turn off for zero third-party "
          "requests."},
    {"key": "autoUpdates", "t": "Automatic updates",
     "d": "Off by default. When on, UPDATE.bat may query the release source "
          "you configured (UPDATE_REPO). Sightware never downloads or replaces "
          "code on its own."},
    {"grp": "App & alerts", "key": "soundAlerts", "t": "Alert sounds",
     "d": "Play a sound when a queue pops, a match is found or a match "
          "ends (the toast always shows either way)."},
    {"key": "startWithWindows", "t": "Start with Windows",
     "d": "Launches Sightware (console-free) when you sign in, via a shortcut "
          "in your Startup folder. Applied when you save settings."},
]


def _center(win, parent, w, h) -> None:
    win.update_idletasks()
    px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    py = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
    win.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")


class _Dialog(tk.Toplevel):
    def __init__(self, app, title: str, w: int, h: int):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg=BG)
        self.transient(app)
        _center(self, app, w, h)
        self.bind("<Escape>", lambda e: self.destroy())


# ── settings ───────────────────────────────────────────────────
class SettingsDialog(_Dialog):
    def __init__(self, app):
        super().__init__(app, "Sightware Settings", 780, 640)
        self._vars: dict[str, tk.BooleanVar | tk.StringVar] = {}
        settings = app.core.all_settings()
        self._per_map = dict(settings.get("perMap") or {})

        scroll = ScrollFrame(self, bg=BG)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner

        # region
        self._section(body, "region")
        row = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        row.pack(fill="x", padx=16, pady=(0, 8))
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        tk.Label(info, text="Region", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(info, text="Auto-detect reads it from your running client. "
                 "Override only if detection fails.", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8), wraplength=520,
                 justify="left").pack(anchor="w")
        region_var = tk.StringVar(value=str(settings.get("region") or "auto"))
        cb = ttk.Combobox(row, textvariable=region_var, state="readonly",
                          width=12, values=["auto", "na", "eu", "ap", "kr",
                                            "latam", "br"])
        cb.pack(side="right", padx=14)
        self._vars["region"] = region_var

        last_grp = None
        for defn in SETTING_DEFS:
            if defn.get("grp") and defn["grp"] != last_grp:
                self._section(body, defn["grp"])
                last_grp = defn["grp"]
            self._toggle_row(body, defn, settings)

        # ui theme (needs restart)
        self._section(body, "appearance")
        theme_row = tk.Frame(body, bg=CARD)
        theme_row.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(theme_row, text="UI theme", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
        theme_cb = ttk.Combobox(theme_row, state="readonly", width=14,
                                values=["signal", "classic", "violet"])
        theme_cb.set(str(self._vars.get("uiTheme").get()
                         if "uiTheme" in self._vars
                         else settings.get("uiTheme", "signal")))
        theme_cb.pack(side="left")
        self._vars["uiTheme"] = theme_cb_var = tk.StringVar(
            value=theme_cb.get())
        theme_cb.configure(textvariable=theme_cb_var)
        tk.Label(theme_row, text="applies instantly", bg=CARD,
                 fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left", padx=8)
        theme_cb_var.trace_add(
            "write", lambda *_a: self.app.apply_theme_variant(
                theme_cb_var.get()))

        # per-map preferences
        self._section(body, "per-map agent preferences")
        pm_wrap = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                           highlightthickness=1, padx=12, pady=10)
        pm_wrap.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(pm_wrap, text="Used by the pick advisor during agent select.", bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 6))
        self._pm_rows = tk.Frame(pm_wrap, bg=CARD)
        self._pm_rows.pack(fill="x")
        for map_name, agent in self._per_map.items():
            self._add_pm_row(map_name, agent)
        ttk.Button(pm_wrap, text="+ Add map preference", style="Ghost.TButton",
                   command=lambda: self._add_pm_row("", "")).pack(anchor="w",
                                                                  pady=(6, 0))

        # buttons
        btns = tk.Frame(self, bg=BG_RAISED, height=56)
        btns.pack(fill="x", side="bottom")
        btns.pack_propagate(False)
        ttk.Button(btns, text="Save settings", style="Accent.TButton",
                   command=self._save).pack(side="right", padx=14, pady=11)
        ttk.Button(btns, text="Privacy", style="Ghost.TButton",
                   command=lambda: PrivacyDialog(self.app)).pack(side="right",
                                                                 padx=6)
        ttk.Button(btns, text="Check for updates", style="Ghost.TButton",
                   command=self._check_updates).pack(side="right", padx=6)
        ttk.Button(btns, text="Backup data…", style="Ghost.TButton",
                   command=self._backup_data).pack(side="right", padx=6)
        ttk.Button(btns, text="Restore backup…", style="Ghost.TButton",
                   command=self._restore_data).pack(side="right", padx=6)
        ttk.Button(btns, text="Open data folder", style="Ghost.TButton",
                   command=self._open_data).pack(side="right", padx=6)
        ttk.Button(btns, text="Quit Sightware", style="Danger.TButton",
                   command=self._quit).pack(side="right", padx=6)

    def _section(self, body, title: str) -> None:
        section_title(body, title).pack(anchor="w", padx=18, pady=(14, 4))

    def _toggle_row(self, body, defn: dict, settings: dict) -> None:
        row = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1)
        row.pack(fill="x", padx=16, pady=2)
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True, padx=14, pady=9)
        tk.Label(info, text=defn["t"], bg=CARD, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(info, text=defn["d"], bg=CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8), wraplength=560,
                 justify="left").pack(anchor="w")
        var = tk.BooleanVar(value=bool(settings.get(defn["key"], False)))
        sw = SwitchHost(row, var)
        sw.pack(side="right", padx=14)
        self._vars[defn["key"]] = var

    def _policy_note(self, body, settings: dict) -> None:
        note = tk.Frame(body, bg=mix(CARD, AMBER, 0.05),
                        highlightbackground=AMBER, highlightthickness=1)
        note.pack(fill="x", padx=16, pady=(2, 8))
        text = ("Policy notice: Riot bans tools that automate agent select "
                "(enforcement began with patch 13.05). Insta-Lock only performs "
                "ONE select+lock of the agent you picked, when YOU press the "
                "button while you are in agent select — the same request the "
                "game's own UI makes, at human speed. It still uses a local "
                "client interface that Riot does not officially document, so "
                "use it at your own risk.")
        tk.Label(note, text=text, bg=note.cget("bg"), fg=TEXT_DIM,
                 font=("Segoe UI", 8), wraplength=560,
                 justify="left").pack(side="left", padx=12, pady=9)
        ack_row = tk.Frame(note, bg=note.cget("bg"))
        ack_row.pack(side="right", padx=10)
        var = tk.BooleanVar(value=bool(settings.get("quickLockPolicyAck")))
        SwitchHost(ack_row, var).pack(anchor="e")
        tk.Label(ack_row, text="I understand\nthe risk", bg=ack_row.cget("bg"),
                 fg=TEXT_DIM, font=("Segoe UI", 7), justify="center").pack()
        self._vars["quickLockPolicyAck"] = var

    def _add_pm_row(self, map_name: str, agent: str) -> None:
        rowf = tk.Frame(self._pm_rows, bg=CARD)
        rowf.pack(fill="x", pady=2)
        map_var = tk.StringVar(value=map_name)
        agent_var = tk.StringVar(value=agent)
        ttk.Combobox(rowf, textvariable=map_var, state="readonly", width=14,
                     values=[""] + MAPS).pack(side="left")
        tk.Label(rowf, text="→", bg=CARD, fg=TEXT_FAINT).pack(side="left",
                                                              padx=8)
        ttk.Combobox(rowf, textvariable=agent_var, state="readonly", width=14,
                     values=[""] + [a["name"] for a in AGENTS]).pack(side="left")
        ttk.Button(rowf, text="✕", style="Ghost.TButton", width=3,
                   command=rowf.destroy).pack(side="left", padx=8)
        rowf.map_var = map_var
        rowf.agent_var = agent_var

    def _save(self) -> None:
        changes = {}
        for key, var in self._vars.items():
            if isinstance(var, tk.BooleanVar):
                changes[key] = bool(var.get())
            else:
                changes[key] = var.get()
        per_map = {}
        for rowf in self._pm_rows.winfo_children():
            m = getattr(rowf, "map_var", None)
            a = getattr(rowf, "agent_var", None)
            if m and a and m.get() and a.get():
                per_map[m.get()] = a.get()
        changes["perMap"] = per_map

        def work():
            merged = self.app.core.update_settings(changes)
            try:
                from .platform_win import set_start_with_windows
                set_start_with_windows(bool(changes.get("startWithWindows")))
            except Exception:
                pass
            return merged

        def done(_merged):
            self.app.toast.show("Settings saved — changes take effect "
                                "immediately.", kind="ok")
            self.app.art_cache.clear_images_all()
            self.app.force_refresh()
            self.destroy()
        self.app.run_bg(work, done, on_error=lambda err: self.app.toast.show(
            f"Couldn't save settings: {err.splitlines()[-1]}", kind="error"))

    def _check_updates(self) -> None:
        def work():
            from .update_check import check_for_update
            return check_for_update()

        def done(res):
            kind = {"up_to_date": "ok", "update_available": "info",
                    "no_repo": "info", "error": "warn"}.get(res["status"], "info")
            self.app.toast.show(res["message"], ms=6000, kind=kind)
        self.app.run_bg(work, done)

    def _backup_data(self) -> None:
        from tkinter import filedialog
        import zipfile
        dest = filedialog.asksaveasfilename(
            title="Backup Sightware data", defaultextension=".zip",
            filetypes=[("Data backup", "*.zip")])
        if not dest:
            return
        data_dir = str(DATA_DIR)
        count = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(data_dir):
                for fn in filenames:
                    if fn.endswith(".tmp"):
                        continue
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, data_dir)
                    zf.write(full, "data/" + rel.replace(os.sep, "/"))
                    count += 1
        self.app.toast.show(f"Backup saved: {count} files.", kind="ok")

    def _restore_data(self) -> None:
        from tkinter import filedialog, messagebox
        import zipfile
        src = filedialog.askopenfilename(
            title="Restore Sightware data backup",
            filetypes=[("Data backup", "*.zip")])
        if not src:
            return
        if not messagebox.askyesno(
                "Restore backup",
                "This will overwrite your current settings, history, "
                "crosshair library and display profiles with the backup "
                "contents. Continue?"):
            return
        data_dir = str(DATA_DIR)
        count = 0
        try:
            with zipfile.ZipFile(src) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    if not name.startswith("data/") or ".." in name:
                        continue
                    rel = name[len("data/"):]
                    dest = os.path.join(data_dir, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(info) as fsrc, open(dest, "wb") as fdst:
                        fdst.write(fsrc.read())
                    count += 1
            self.app.toast.show(f"Restored {count} files — restart Sightware "
                                "to see everything.", kind="ok")
        except Exception as e:
            messagebox.showerror("Restore failed", str(e))

    def _open_data(self) -> None:
        try:
            os.startfile(str(DATA_DIR))  # noqa: S606
        except (OSError, AttributeError):
            self.app.toast.show(f"Data folder: {DATA_DIR}", kind="info")

    def _quit(self) -> None:
        if getattr(self, "_quit_armed", 0):
            self.destroy()
            self.app.quit_app()
            return
        self._quit_armed = 1
        self.after(4000, lambda: setattr(self, "_quit_armed", 0))
        self.app.toast.show("Click Quit again to stop Sightware completely.",
                            kind="warn")


class SwitchHost(tk.Frame):
    """BooleanVar-backed toggle used by the settings dialog."""

    def __init__(self, master, var: tk.BooleanVar):
        super().__init__(master, bg=master.cget("bg"))
        self.var = var
        self.sw = Switch(self, on=var.get(),
                         command=lambda: var.set(self.sw.on))
        self.sw.pack()


# ── match detail ───────────────────────────────────────────────
class MatchDetailDialog(_Dialog):
    _PARTY_COLORS = ["#FF7A1A", "#35C98A", "#57B4E8", "#F5B942", "#C4B1FA"]

    def __init__(self, app, match_id: str, subject: str | None = None,
                 highlight_puuid: str | None = None):
        super().__init__(app, "Match report", 1000, 760)
        self.match_id = match_id
        self.subject = subject
        self.highlight_puuid = highlight_puuid
        loading = tk.Label(self, text="Loading match…", bg=BG, fg=TEXT_DIM,
                           font=("Segoe UI", 10))
        loading.pack(pady=30)

        def work():
            return app.core.match_detail(match_id, subject)

        def done(data):
            loading.destroy()
            if data.get("error"):
                tk.Label(self, text=data["error"], bg=BG, fg=LOSS,
                         font=("Segoe UI", 10)).pack(pady=20)
                return
            try:
                self._render(data)
            except Exception:
                import traceback
                err = traceback.format_exc()
                tk.Label(self, text="Render error: " + err.splitlines()[-1],
                         bg=BG, fg=LOSS, font=("Segoe UI", 9),
                         wraplength=800).pack(pady=20)
        app.run_bg(work, done, on_error=lambda e: (loading.destroy(),
                     tk.Label(self, text=f"Failed: {e.splitlines()[-1]}",
                              bg=BG, fg=LOSS).pack(pady=20)))

    def _render(self, data: dict) -> None:
        head = tk.Frame(self, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1, padx=16, pady=10)
        head.pack(fill="x", padx=14, pady=(14, 6))
        res = data.get("result")
        scores = data.get("scores") or {}
        subject_team = next((p.get("team") for p in data.get("players", [])
                             if p.get("isSubject")), None)
        other = next((t for t in scores if t != subject_team), None)
        color = {"Victory": WIN, "Defeat": LOSS}.get(res, TEXT)
        tk.Label(head, text=res or "MATCH", bg=CARD, fg=color,
                 font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(head, bg=CARD, fg=TEXT, font=("Segoe UI", 16, "bold"),
                 text=f"  {scores.get(subject_team, '?')}–{scores.get(other, '?')}"
                      if subject_team else "").pack(side="left")
        tk.Label(head, text="  ·  ".join(
            x for x in (data.get("map"), data.get("mode")) if x),
            bg=CARD, fg=TEXT_DIM, font=("Segoe UI", 10)).pack(side="left",
                                                              padx=14)

        # match meta (note / tags / bookmark)
        meta_row = tk.Frame(self, bg=BG)
        meta_row.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(meta_row, text="NOTE", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.note_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.book_var = tk.BooleanVar()
        ttk.Entry(meta_row, textvariable=self.note_var, width=36).pack(
            side="left", padx=(8, 6))
        tk.Label(meta_row, text="TAGS (comma-sep)", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        ttk.Entry(meta_row, textvariable=self.tags_var, width=20).pack(
            side="left", padx=(8, 6))
        ttk.Checkbutton(meta_row, text="★ Bookmark",
                        variable=self.book_var).pack(side="left", padx=4)
        ttk.Button(meta_row, text="Save meta", style="Ghost.TButton",
                   command=self._save_meta).pack(side="left", padx=6)
        self._load_meta()

        scroll = ScrollFrame(self, bg=BG)
        scroll.pack(fill="both", expand=True, padx=0, pady=(0, 12))
        body = scroll.inner

        teams: dict[str, list] = {}
        for p in data.get("players") or []:
            teams.setdefault(p.get("team") or "?", []).append(p)

        # party detection: group players by partyId within each team
        party_colors: dict[str, str] = {}
        pi = 0
        for team_players in teams.values():
            seen_pids: dict[str, None] = {}
            for p in team_players:
                pid = p.get("partyId") or ""
                if pid and p.get("partyId") not in seen_pids:
                    seen_pids[pid] = None
            # assign colors to parties of 2+
            pid_counts: dict[str, int] = {}
            for p in team_players:
                pid = p.get("partyId") or ""
                if pid:
                    pid_counts[pid] = pid_counts.get(pid, 0) + 1
            for pid, count in pid_counts.items():
                if count >= 2:
                    party_colors[pid] = self._PARTY_COLORS[pi % len(self._PARTY_COLORS)]
                    pi += 1

        for team_id, players in teams.items():
            if subject_team:
                label = "YOUR TEAM" if team_id == subject_team else "ENEMY TEAM"
            else:
                label = f"TEAM {team_id}"
            # avg rank badge for this team
            ts_info = (data.get("teamStats") or {}).get(team_id) or {}
            avg_rank = ts_info.get("avgRank", "")
            head_frame = tk.Frame(body, bg=BG)
            head_frame.pack(fill="x", padx=16, pady=(10, 4))
            section_head(head_frame, label, bg=BG).pack(side="left")
            if avg_rank:
                tk.Label(head_frame, text=f"avg rank: {avg_rank}", bg=BG,
                         fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(
                    side="left", padx=(10, 0))
            rows = []
            for p in players:
                name = p.get("name") or "—"
                if p.get("isSelf"):
                    name += "  (you)"
                elif p.get("isSubject"):
                    name += "  (viewed player)"
                if p.get("isMatchMvp"):
                    name += "  ★"
                # party badge
                party_badge = ""
                party_color = None
                pid = p.get("partyId") or ""
                if pid and pid in party_colors:
                    party_badge = f"  [{chr(0x25CF)}]"
                    party_color = party_colors[pid]
                is_highlight = (self.highlight_puuid and
                                p.get("puuid") == self.highlight_puuid)
                fb = p.get("firstBloods")
                fd = p.get("firstDeaths")
                rows.append({
                    "cells": {
                        "agent": p.get("agent") or "—",
                        "name": name + party_badge,
                        "kills": str(p.get("kills", 0)),
                        "deaths": str(p.get("deaths", 0)),
                        "assists": str(p.get("assists", 0)),
                        "kd": str(p.get("kd", "—")) if p.get("kd") is not None else "—",
                        "acs": str(p.get("acs", 0)) if p.get("acs") is not None else "—",
                        "hs": f"{p.get('hsPct')}%" if p.get("hsPct") is not None else "—",
                        "adr": str(p.get("adr")) if p.get("adr") is not None else "—",
                        "fb": str(fb) if fb is not None else "—",
                        "fd": str(fd) if fd is not None else "—",
                        "mk": str(p.get("multiKills")) if p.get("multiKills") is not None else "—",
                        "aces": str(p.get("aces")) if p.get("aces") is not None else "—",
                        "rank": p.get("rank") or "—",
                        "lvl": str(p.get("level") or "—"),
                    },
                    "colors": {
                        "agent": readable(p.get("agentColor") or TEXT_DIM),
                        "rank": p.get("rankColor") or TEXT,
                        "name": party_color or TEXT,
                        "result": party_color or TEXT,
                    },
                    "icons": {"agent": p.get("agentPortrait")},
                    "accent": RED if p.get("isSelf") else (
                        PURPLE if is_highlight else None),
                    "bg": mix(CARD, RED, 0.06) if p.get("isSelf") else (
                        mix(CARD, PURPLE, 0.08) if is_highlight else None),
                })
            table = DataTable(body, [
                Column("agent", "Agent", 92),
                Column("name", "Player", 160, stretch=True),
                Column("kills", "K", 40, "e"), Column("deaths", "D", 40, "e"),
                Column("assists", "A", 40, "e"), Column("kd", "K/D", 48, "e"),
                Column("acs", "ACS", 50, "e"),
                Column("hs", "HS%", 48, "e"), Column("adr", "ADR", 48, "e"),
                Column("fb", "FB", 38, "e"), Column("fd", "FD", 38, "e"),
                Column("mk", "Multi", 42, "e"),
                Column("aces", "Aces", 42, "e"),
                Column("rank", "Rank", 100), Column("lvl", "Lvl", 38, "e"),
            ], height=27 * max(1, len(rows)) + 34, row_h=27, zebra=True)
            table.set_rows(rows)
            table.pack(fill="x", padx=16)
            cache = getattr(self.app, "art_cache", None)
            if cache:
                for idx, row in enumerate(rows):
                    url = row["icons"].get("agent")
                    if url:
                        photo = cache.get(url, target=22)
                        if photo:
                            row["icons"]["agent"] = photo

        rounds = data.get("rounds") or []
        if rounds:
            section_title(body, "round timeline (your rounds)").pack(
                anchor="w", padx=16, pady=(12, 4))
            strip = tk.Frame(body, bg=BG)
            strip.pack(fill="x", padx=16)
            for r in rounds[:50]:
                color = WIN if r.get("won") else LOSS
                cell = tk.Label(strip, text=str(r.get("n", "")),
                                bg=mix(BG, color, 0.55), fg="#FFFFFF",
                                font=("Segoe UI", 7), width=3, pady=2)
                cell.pack(side="left", padx=1)

    def _load_meta(self) -> None:
        def work():
            return self.app.core.get_match_meta(self.match_id)

        def done(meta):
            self.note_var.set(meta.get("note") or "")
            self.tags_var.set(", ".join(meta.get("tags") or []))
            self.book_var.set(bool(meta.get("bookmarked")))
        self.app.run_bg(work, done)

    def _save_meta(self) -> None:
        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        body = {"note": self.note_var.get(), "tags": tags,
                "bookmarked": bool(self.book_var.get())}

        def work():
            return self.app.core.set_match_meta(self.match_id, body)

        def done(res):
            ok = res.get("ok")
            self.app.toast.show("Match meta saved." if ok else
                                (res.get("message") or "Couldn't save meta."),
                                kind="ok" if ok else "warn")
        self.app.run_bg(work, done)


# ── player profile ─────────────────────────────────────────────
class PlayerProfileDialog(_Dialog):
    def __init__(self, app, puuid: str, name: str | None = None):
        super().__init__(app, f"Player — {name or puuid[:8]}", 940, 700)
        self.puuid = puuid
        loading = tk.Label(self, text="Loading player…", bg=BG, fg=TEXT_DIM,
                           font=("Segoe UI", 10))
        loading.pack(pady=30)

        def work():
            return app.core.player(puuid)

        def done(data):
            loading.destroy()
            if data.get("error"):
                tk.Label(self, text=data["error"], bg=BG, fg=LOSS,
                         font=("Segoe UI", 10)).pack(pady=20)
                return
            self._render(data)
        app.run_bg(work, done, on_error=lambda e: (loading.destroy(),
                     tk.Label(self, text=f"Failed: {e.splitlines()[-1]}",
                              bg=BG, fg=LOSS).pack(pady=20)))

    def _render(self, data: dict) -> None:
        head = tk.Frame(self, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1, padx=16, pady=10)
        head.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(head, text=data.get("riotId", "Player"), bg=CARD, fg=TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        live = data.get("source") == "local"
        tk.Label(head, text=("LIVE · local client" if live
                             else f"source: {data.get('source', 'demo')}"),
                 bg=CARD, fg=TEAL if live else TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(side="left", padx=10)
        for label, value, color in (
                ("RANK", data.get("currentRank", "—"),
                 data.get("rankColor") or TEXT),
                ("RR", str(data.get("rr", 0)), TEXT),
                ("PEAK", data.get("peakRank", "—"),
                 data.get("peakColor") or TEXT_DIM)):
            box = tk.Frame(head, bg=CARD)
            box.pack(side="right", padx=10)
            tk.Label(box, text=label, bg=CARD, fg=TEXT_FAINT,
                     font=("Segoe UI", 7, "bold")).pack()
            tk.Label(box, text=value, bg=CARD, fg=color,
                     font=("Segoe UI", 11, "bold")).pack()

        av = data.get("averages") or {}
        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", padx=16, pady=(4, 4))
        for title, value, sub in (
                ("last games", str(av.get("matchesAnalyzed", 0)),
                 f"{av.get('wins', 0)}W · {av.get('losses', 0)}L"),
                ("win rate", f"{av.get('winRate', 0)}%", "recent form"),
                ("k / d", str(av.get("kd", 0)), f"{av.get('kills', 0)} K · "
                 f"{av.get('deaths', 0)} D avg"),
                ("headshot", f"{av.get('hsPct', 0)}%", "average"),
                ("suggestion", data.get("pickSuggestion", {}).get("agent") or "—",
                 "from their history")):
            c = tk.Frame(cards, bg=CARD, highlightbackground=LINE,
                         highlightthickness=1, padx=12, pady=8)
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)
            tk.Label(c, text=title.upper(), bg=CARD, fg=TEXT_FAINT,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
            tk.Label(c, text=value, bg=CARD, fg=TEXT,
                     font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(c, text=sub, bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 7)).pack(anchor="w")

        scroll = ScrollFrame(self, bg=BG)
        scroll.pack(fill="both", expand=True, padx=0, pady=(6, 12))
        body = scroll.inner

        section_title(body, "recent matches").pack(anchor="w", padx=16,
                                                   pady=(8, 4))
        rows = []
        for m in data.get("matches") or []:
            st = m.get("stats") or {}
            result = m.get("result")
            rows.append({
                "cells": {
                    "date": _short_ts(m.get("date")),
                    "result": result or "—",
                    "score": f"{m.get('roundsWon', 0)}–{m.get('roundsLost', 0)}",
                    "agent": m.get("agent") or "—",
                    "map": m.get("map") or "—",
                    "mode": m.get("mode") or "—",
                    "kd": str(st.get("kda", "—")),
                    "acs": str(st.get("acs", "—")),
                },
                "colors": {
                    "result": WIN if result == "Victory"
                              else LOSS if result == "Defeat" else TEXT_DIM,
                    "agent": (m.get("agentMeta") or {}).get("color") or TEXT_DIM,
                },
                "data": {"matchId": m.get("matchId"), "subject": self.puuid},
            })
        table = DataTable(body, [
            Column("date", "Date", 130),
            Column("result", "Result", 74),
            Column("score", "Score", 58, "e"),
            Column("agent", "Agent", 92),
            Column("map", "Map", 92),
            Column("mode", "Mode", 100),
            Column("kd", "K/D", 52, "e"),
            Column("acs", "ACS", 54, "e"),
        ], height=27 * max(1, len(rows)) + 34, row_h=27,
            on_row_click=self._open_match)
        table.set_rows(rows)
        table.pack(fill="x", padx=16)

        co = data.get("coPlayers") or []
        if co:
            section_title(body, "plays with").pack(anchor="w", padx=16,
                                                   pady=(12, 4))
            for mate in co[:6]:
                rowf = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                                highlightthickness=1)
                rowf.pack(fill="x", padx=16, pady=1)
                tk.Label(rowf, text=mate.get("name") or "—", bg=CARD, fg=TEXT,
                         font=("Segoe UI", 9)).pack(side="left", padx=12,
                                                    pady=5)
                tk.Label(rowf, text=f"{mate.get('sharedMatches', 0)} shared matches"
                         + (" · party" if mate.get("isParty") else ""),
                         bg=CARD, fg=TEXT_DIM,
                         font=("Segoe UI", 8)).pack(side="left", padx=8)

    def _open_match(self, data: dict) -> None:
        if data.get("matchId"):
            # always use the LOCAL player as subject so the Riot client
            # returns complete match data; highlight the encounter player
            import encounter_log
            accounts = list(encounter_log._load().get("accounts", {}).keys())
            local_puuid = accounts[0] if accounts else None
            MatchDetailDialog(self.app, data["matchId"], subject=local_puuid,
                              highlight_puuid=self.puuid)


# ── privacy ────────────────────────────────────────────────────
class PrivacyDialog(_Dialog):
    def __init__(self, app):
        super().__init__(app, "Privacy — what leaves this PC", 640, 520)
        info = app.core.privacy()
        scroll = ScrollFrame(self, bg=BG)
        scroll.pack(fill="both", expand=True)
        body = scroll.inner
        section_title(body, "privacy posture").pack(anchor="w", padx=18,
                                                    pady=(16, 6))
        for key, text in info.items():
            if key == "dataLeaving":
                continue
            row = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                           highlightthickness=1)
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(row, text=key, bg=CARD, fg=TEAL,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12,
                                                        pady=(7, 0))
            tk.Label(row, text=text, bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 9), wraplength=540,
                     justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        section_title(body, "network destinations").pack(anchor="w", padx=18,
                                                         pady=(12, 6))
        for dest in info.get("dataLeaving") or []:
            row = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                           highlightthickness=1)
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(row, text=dest.get("destination", ""), bg=CARD, fg=TEXT,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12,
                                                        pady=(7, 0))
            tk.Label(row, text=dest.get("what", ""), bg=CARD, fg=TEXT_DIM,
                     font=("Segoe UI", 8), wraplength=540,
                     justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        tk.Label(body, text="No web server runs in the GUI edition — the old "
                 "127.0.0.1:5000 dashboard is gone; the desktop app is the only UI.",
                 bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8),
                 wraplength=560, justify="left").pack(anchor="w", padx=18,
                                                      pady=(12, 16))


def _short_ts(iso: str | None) -> str:
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        return dt.astimezone().strftime("%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return "—"
