"""Sightware GUI — Live Board tab.

Mirrors the original web dashboard: single centered column, one combined
team table with "// YOUR TEAM" / "// ENEMY TEAM" section rows, two-line
rank & peak cells (icon + name + RR/act sub-line), party-colored underlines
under names, a gold agent-lock bar during Agent Select, and the sortable
FINAL match scoreboard below. No page scrolling.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme import (AMBER, BG, CARD, LINE, LINE_SOFT, ORANGE, RED, RED_SOFT,
                   TEAL, TEAL_DIM, TEXT, TEXT_DIM, TEXT_FAINT, WIN, LOSS,
                   mix, multi_stop, readable)
from ..widgets import (Banner, DataTable, Column, ScrollFrame, cover_crop)

from agents import AGENTS
from ..dialogs import MatchDetailDialog, PlayerProfileDialog

TEAM_COLS = [
    Column("party", "", 34, "center", sortable=False),
    Column("agent", "Agent", 118),
    Column("name", "Name", 168, stretch=True, minw=150),
    Column("rank", "Rank", 122),
    Column("peak", "Peak", 122),
    Column("prev", "Prev", 92),
    Column("lvl", "Lvl", 50, "e"),
    Column("stats", "HS / WR / K&D", 160, "e", sortable=False),
    Column("enc", "Enc.", 72, "e", sortable=False),
]

FS_COLS = [
    Column("pos", "#", 30, "center", sortable=False),
    Column("agent", "Agent", 96),
    Column("name", "Player", 200, stretch=True),
    Column("score", "Score", 64, "e"),
    Column("acs", "ACS", 56, "e"),
    Column("kills", "K", 44, "e"),
    Column("deaths", "D", 44, "e"),
    Column("assists", "A", 44, "e"),
    Column("ultsUsed", "Ult", 44, "e"),
]

SECTION_H = 30


def _section_row(label: str, color: str) -> dict:
    return {"section": label, "section_color": color, "data": {}}


def _num(v) -> str:
    return "–" if v is None else str(v)


class LiveTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.core = app.core
        self._last_board: dict = {}

        # page scroll ONLY when content overflows (tables no longer
        # hijack the wheel unless they overflow themselves)
        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner

        # pack order (top→bottom): riots, notice, assistant, hero, table…
        self.riots_lbl = tk.Label(body, text="", bg=BG, fg=TEXT_FAINT,
                                  font=("Segoe UI", 8))
        self.riots_lbl.pack(fill="x", anchor="w", pady=(0, 4))
        self.notice = Banner(body, "", "info")
        self.assistant = AssistantBanner(body, app)
        self.hero = MatchHero(body, app)

        # combined team table (web-dashboard style)
        self.team_table = DataTable(body, TEAM_COLS, height=280, row_h=46,
                                    on_row_click=self._open_row,
                                    auto_height=True)
        self.team_table.pack(fill="x", pady=(8, 0))

        self.parties_lbl = tk.Label(body, text="", bg=BG, fg=TEXT_DIM,
                                    font=("Segoe UI", 8))
        self.parties_lbl.pack(fill="x", anchor="w", pady=(5, 0))

        # match scoreboard header row
        self.fs_head = tk.Frame(body, bg=BG)
        self.fs_head.pack(fill="x", pady=(16, 4))
        tk.Frame(self.fs_head, bg=RED, width=3, height=14).pack(
            side="left", padx=(0, 8))
        tk.Label(self.fs_head, text="MATCH SCOREBOARD", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.fs_chip = tk.Label(self.fs_head, text="", bg=BG, fg=TEXT_FAINT,
                                font=("Segoe UI", 8))
        self.fs_chip.pack(side="left", padx=10)
        self.fs_report_btn = ttk.Button(self.fs_head, text="Full match report",
                                        style="Ghost.TButton",
                                        command=self._open_match_report)
        self.fs_report_btn.pack(side="right")
        self.fs_banner = tk.Label(self.fs_head, text="", bg=BG,
                                  font=("Segoe UI", 11, "bold"))
        self.fs_banner.pack(side="right", padx=10)
        self._fs_match_id: str | None = None

        self.fs_table = DataTable(body, FS_COLS, height=322, row_h=28,
                                  on_row_click=self._open_row)
        self.fs_table.pack(fill="x", pady=(0, 4))
        self.fs_note = tk.Label(
            body, justify="left", bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8),
            anchor="w",
            text="Riot's local APIs expose no per-player stats (or live ult "
                 "points) while a match runs — the table fills in the moment "
                 "your client publishes the final data.")
        self.fs_note.pack(fill="x", anchor="w", pady=(0, 10))

    # ── helpers ────────────────────────────────────────────────
    def on_show(self) -> None:
        if self._last_board:
            self.update_board(self._last_board)

    def _open_row(self, data: dict) -> None:
        if not data or not data.get("puuid"):
            return
        PlayerProfileDialog(self.app, data["puuid"], data.get("name"))

    def _open_match_report(self) -> None:
        if not self._fs_match_id:
            self.app.toast.show("No finished match to report yet.", kind="info")
            return
        board = self._last_board or {}
        MatchDetailDialog(self.app, self._fs_match_id,
                          subject=board.get("selfPuuid"))

    # ── board render ───────────────────────────────────────────
    def update_board(self, board: dict) -> None:
        self._last_board = board
        reqs = board.get("riotRequests")
        self.riots_lbl.configure(
            text=f"Riot requests this session: {reqs}"
                 if reqs is not None else "")
        notice = board.get("notice") or {}
        self.notice.show(notice.get("message"), notice.get("level", "info"))
        self.assistant.update_board(board)
        self.hero.update_board(board)

        teams = board.get("teams") or {}
        self_team = board.get("selfTeam") or "Blue"
        state = board.get("state")

        rows: list[dict] = [_section_row("// YOUR TEAM", TEAL)]
        rows += self._team_rows(teams.get(self_team) or [])
        enemy = next((t for t in teams if t != self_team), None)
        enemy_players = teams.get(enemy) or []
        show_enemy = (enemy is not None
                      and (state == "INGAME" or board.get("source") == "demo"
                           or any(p.get("kd") is not None
                                  for p in enemy_players)))
        if show_enemy:
            rows.append(_section_row("// ENEMY TEAM", "#C96A74"))
            rows += self._team_rows(enemy_players)
        self.team_table.set_rows(rows)
        self._attach_icons(self.team_table, rows)

        parts = board.get("parties") or []
        if parts:
            self.parties_lbl.configure(text="Parties:  " + "   ·   ".join(
                f"●{p['number']} {p['size']}-stack" for p in parts))
        else:
            self.parties_lbl.configure(text="")

        self._render_final(board)

    def _team_rows(self, players: list[dict]) -> list[dict]:
        rows = []
        for p in players:
            kd = p.get("kd")
            kd_color = TEXT
            kd_text = "…"
            if kd is not None:
                kd_text = f"{kd:.2f}"
                kd_color = WIN if kd >= 1.3 else (TEXT if kd >= 1.0 else LOSS)
            elif not p.get("statsPending"):
                kd_text = "—"
            hs = p.get("hsPct")
            wr = p.get("winRate")
            stats_segments = [
                (f"{hs}%" if hs is not None else "—", TEXT_DIM),
                (" / ", TEXT_FAINT),
                (f"{wr}%" if wr is not None else "—", TEXT_DIM),
                (" / ", TEXT_FAINT),
                (kd_text, kd_color),
            ]
            rank_main = p.get("rank") or "—"
            rank_sub = ""
            rr = p.get("rr")
            if rr and (p.get("rankTier") or 0) > 2:
                rank_sub = f"{rr} RR"
            if p.get("leaderboard"):
                rank_sub = (rank_sub + "  ·  " if rank_sub else "") \
                    + f"#{p['leaderboard']:,}"
            peak_main = p.get("peakRank") or "—"
            peak_sub = p.get("peakAct") or ""
            party = p.get("party") or {}
            party_color = party.get("color")
            rows.append({
                "cells": {
                    "party": f"●{party['number']}" if party else "",
                    "agent": p.get("agent") or "—",
                    "name": (p.get("name") or "—")
                            + (" (you)" if p.get("isSelf") else ""),
                    "rank": {"main": rank_main, "sub": rank_sub},
                    "peak": {"main": peak_main, "sub": peak_sub},
                    "prev": p.get("previousRank") or "—",
                    "lvl": str(p.get("level") or "—")
                           + (" *" if p.get("levelHidden") else ""),
                    "stats": stats_segments,
                    "enc": self._enc_text(p),
                },
                "colors": {
                    "party": readable(party_color or TEXT_DIM),
                    "agent": readable(p.get("agentColor") or TEXT_DIM),
                    "rank": p.get("rankColor") or TEXT,
                    "peak": p.get("peakColor") or TEXT_DIM,
                    "prev": TEXT_DIM,
                    "name": TEXT if not p.get("nameHidden") else TEXT_DIM,
                },
                "fonts": {"name": ("Segoe UI", 10, "bold")},
                "icons": {"rank": p.get("rankIcon"),
                          "agent": p.get("agentPortrait")},
                "underline_color": party_color,
                "accent": RED if p.get("isSelf") else party_color,
                "bg": mix(CARD, RED, 0.07) if p.get("isSelf") else None,
                "data": {"puuid": p.get("puuid"), "name": p.get("name")},
            })
        return rows

    @staticmethod
    def _enc_text(p: dict) -> str:
        enc = p.get("encounter") or {}
        total = (enc.get("withCount") or 0) + (enc.get("againstCount") or 0)
        if not total:
            return ""
        return f"{enc.get('withCount', 0)}W / {enc.get('againstCount', 0)}A"

    def _attach_icons(self, table: DataTable, rows: list[dict]) -> None:
        cache = getattr(self.app, "art_cache", None)
        if not cache:
            return
        pending = False
        for row in rows:
            for key, target in (("rank", 22), ("agent", 26)):
                url = (row.get("icons") or {}).get(key)
                if not url:
                    continue
                photo = cache.get(url, target=target)
                if photo:
                    row["icons"][key] = photo
                else:
                    pending = True
                    cache.when_ready(url, lambda: self.after_idle(
                        lambda: self._refresh_icons(table)))
        # always repaint: on a warm cache the photos replaced the URLs
        # AFTER set_rows already drew the table
        table.redraw()

    def _refresh_icons(self, table: DataTable) -> None:
        rows = table.rows()
        cache = getattr(self.app, "art_cache", None)
        if not cache or not rows:
            return
        for row in rows:
            for key, target in (("rank", 22), ("agent", 26)):
                url = (row.get("icons") or {}).get(key)
                if isinstance(url, str):
                    photo = cache.get(url, target=target)
                    if photo:
                        row["icons"][key] = photo
        table.redraw()

    # ── final scoreboard card ──────────────────────────────────
    def _render_final(self, board: dict) -> None:
        fs = board.get("finalScoreboard")
        state = board.get("state")
        demo = board.get("source") == "demo"
        rows = (fs or {}).get("players") if isinstance(fs, dict) else None
        self._fs_match_id = ((fs or {}).get("matchId")
                             if isinstance(fs, dict) else None)

        if not rows:
            if state == "INGAME":
                self._render_running(board)
            else:
                self._hide_final()
            return

        self.fs_head.pack(fill="x", pady=(16, 4))
        self.fs_table.pack(fill="x", pady=(0, 4))
        self.fs_note.pack(fill="x", anchor="w", pady=(0, 10))
        self.fs_chip.configure(
            text=("DEMO" if (demo or (fs or {}).get("demo")) else "FINAL")
                 + "  ·  sort: click a column header")
        res = (fs or {}).get("result")
        self.fs_banner.configure(
            text=self._result_text(fs),
            fg={"Victory": WIN, "Defeat": LOSS}.get(res, TEXT_DIM),
            bg=(mix(BG, WIN, 0.10) if res == "Victory"
                else mix(BG, LOSS, 0.10) if res == "Defeat" else BG),
            padx=12, pady=3)

        table_rows = []
        for i, p in enumerate(rows):
            name = p.get("name") or "—"
            if p.get("isSelf"):
                name += "  (you)"
            if p.get("isMatchMvp"):
                name += "  ★"
            table_rows.append({
                "cells": {
                    "pos": str(i + 1),
                    "agent": p.get("agent") or "—",
                    "name": name,
                    "score": _num(p.get("score")),
                    "acs": _num(p.get("acs")),
                    "kills": _num(p.get("kills")),
                    "deaths": _num(p.get("deaths")),
                    "assists": _num(p.get("assists")),
                    "ultsUsed": _num(p.get("ultsUsed")),
                },
                "colors": {
                    "agent": readable(p.get("agentColor") or TEXT_DIM),
                    "name": TEXT,
                    "pos": TEXT_FAINT,
                },
                "icons": {"agent": p.get("agentPortrait")},
                "accent": RED if p.get("isSelf") else None,
                "bg": mix(CARD, RED, 0.06) if p.get("isSelf") else None,
                "data": {"puuid": p.get("puuid")},
            })
        self.fs_table.set_rows(table_rows)
        if self.fs_table._sort_key is None:
            self.fs_table.set_sort("score", -1)
        self._attach_fs_icons(table_rows)

    def _attach_fs_icons(self, rows: list[dict]) -> None:
        cache = getattr(self.app, "art_cache", None)
        if not cache:
            return
        for row in rows:
            url = row["icons"].get("agent")
            if not url:
                continue
            photo = cache.get(url, target=22)
            if photo:
                row["icons"]["agent"] = photo
            else:
                cache.when_ready(url, lambda: self.after_idle(
                    lambda: self.fs_table.redraw()))

    def _result_text(self, fs: dict) -> str:
        if not fs:
            return ""
        res = fs.get("result")
        scores = fs.get("scores") or {}
        self_team = fs.get("selfTeam") or "Blue"
        other = next((t for t in scores if t != self_team), None)
        sc = f"{scores.get(self_team, '?')}–{scores.get(other, '?')}" \
            if other is not None else ""
        parts = [p for p in (res, sc, fs.get("map"), fs.get("mode")) if p]
        return "   ".join(parts)

    def _render_running(self, board: dict) -> None:
        self.fs_head.pack(fill="x", pady=(16, 4))
        self.fs_table.pack(fill="x", pady=(0, 4))
        self.fs_note.pack(fill="x", anchor="w", pady=(0, 10))
        held = bool(board.get("held"))
        sc = board.get("score") or {}
        chip = "LAST MATCH" if held else "MATCH RUNNING"
        rd = ("final" if held
              else f"round {sc.get('round')}" if sc.get("round") is not None
              else "")
        self.fs_chip.configure(text=chip + (f"  ·  {rd}" if rd else ""))
        self.fs_banner.configure(
            text=f"{sc.get('ally', 0)} : {sc.get('enemy', 0)}",
            fg=RED_SOFT if not held else TEXT_DIM, bg=BG, padx=0, pady=0)
        placeholder = [{
            "cells": {"pos": "", "agent": "",
                      "name": "—" if not held
                              else "Waiting for Riot to publish the final data…",
                      "score": "", "acs": "", "kills": "", "deaths": "",
                      "assists": "", "ultsUsed": ""},
            "colors": {"name": TEXT_FAINT},
            "data": {},
        }]
        self.fs_table.set_rows(placeholder)

    def _hide_final(self) -> None:
        self.fs_head.pack_forget()
        self.fs_table.pack_forget()
        self.fs_note.pack_forget()


class MatchHero(tk.Canvas):
    """Web-dashboard style hero: map name + mode chip, gold lock bar during
    Agent Select, score + win-probability strip in game, splash art right."""

    HEIGHT = 112

    def __init__(self, master, app):
        super().__init__(master, bg=CARD, height=self.HEIGHT,
                         highlightthickness=1, highlightbackground=LINE, bd=0)
        self.app = app
        self._board: dict = {}
        self._splash = None
        self._splash_url: str | None = None
        self._redraw_job: str | None = None
        self.bind("<Configure>", self._queue_redraw)
        self.pack(fill="x", pady=(10, 0))
        self.after(150, self.redraw)

    def _queue_redraw(self, _evt=None) -> None:
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(30, self.redraw)

    def update_board(self, board: dict) -> None:
        self._board = board
        self._load_splash(board)
        self.redraw()

    def _load_splash(self, board: dict) -> None:
        url = board.get("mapSplash") or ""
        if not url and board.get("map"):
            try:
                from valapi import map_splash
                url = map_splash(board["map"])
            except Exception:
                url = ""
        if not url or url == self._splash_url:
            return
        cache = getattr(self.app, "art_cache", None)
        if not cache or not cache.load_art_enabled():
            return
        self._splash_url = url
        self._splash = None
        photo = cache.get(url)
        if photo is not None:
            self._set_splash(photo)
        else:
            cache.when_ready(url, self._set_splash)

    def _set_splash(self, photo) -> None:
        try:
            self._splash = photo
            self.after_idle(self.redraw)
        except Exception:
            pass

    def redraw(self) -> None:
        self._redraw_job = None
        self.delete("all")
        w = self.winfo_width() or 1000
        h = self.HEIGHT
        board = self._board or {}

        for y in range(h):
            self.create_line(0, y, w, y,
                             fill=multi_stop(["#182634", "#101A24"],
                                             y / (h - 1)))

        panel_w = 0
        img = self._splash
        if img is not None:
            panel_w = max(240, int(w * 0.40))
            cropped = cover_crop(img, panel_w, h)
            if cropped is not None:
                self._splash_drawn = cropped  # keep a reference (GC!)
                self.create_image(w, 0, image=cropped, anchor="ne")
            else:
                panel_w = 0
        if panel_w == 0:
            self.create_text(w - 28, h // 2,
                             text=(board.get("map") or "SIGHTWARE").upper(),
                             fill=mix("#151B27", "#F5F7FA", 0.06),
                             font=("Segoe UI", 36, "bold"), anchor="e")

        text_right = w - panel_w - 24

        self.create_text(24, 24, text=(board.get("map") or "—").upper(),
                         fill=TEXT, font=("Segoe UI", 19, "bold"), anchor="w")
        chip_y = 48
        mode = board.get("mode") or ""
        cx_cursor = 24
        if mode:
            cw = 14 + len(mode) * 7
            self.create_rectangle(cx_cursor, chip_y, cx_cursor + cw,
                                  chip_y + 21,
                                  fill=mix("#151B27", "#F5F7FA", 0.03),
                                  outline="#2A3844")
            self.create_text(cx_cursor + cw / 2, chip_y + 10,
                             text=mode.upper(), fill=TEXT_DIM,
                             font=("Segoe UI", 8, "bold"), anchor="center")
            cx_cursor += cw + 8
        side = board.get("side")
        if side:
            self.create_text(cx_cursor + 4, chip_y + 10,
                             text=f"{side.upper()} SIDE", fill=TEAL,
                             font=("Segoe UI", 8, "bold"), anchor="w")

        sc = board.get("score")
        state = board.get("state")
        score_cx = 24 + (text_right - 24) // 2
        if sc:
            self.create_text(
                score_cx, 30,
                text=f"{sc.get('ally', 0)}  :  {sc.get('enemy', 0)}",
                fill=TEXT, font=("Segoe UI", 22, "bold"), anchor="center")
            rd = sc.get("round")
            if rd is not None:
                self.create_text(score_cx, 56, text=f"ROUND {rd}",
                                 fill=TEXT_DIM, font=("Segoe UI", 8, "bold"),
                                 anchor="center")
        elif state == "PREGAME":
            self.create_text(score_cx, 38, text="AGENT SELECT", fill=TEAL,
                             font=("Segoe UI", 13, "bold"), anchor="center")

        lp = board.get("lockProgress")
        wp = board.get("winProb")
        bar_h = 6
        zone_w = text_right - 24
        if lp and state == "PREGAME":
            pct = lp.get("locked", 0) / max(1, lp.get("total", 1))
            self.create_text(24, h - 36, text="AGENTS LOCKED", fill=TEXT_FAINT,
                             font=("Segoe UI", 7, "bold"), anchor="w")
            self.create_text(text_right, h - 36,
                             text=f"{lp.get('locked', 0)}/{lp.get('total', 1)}",
                             fill="#F5C542", font=("Segoe UI", 8, "bold"),
                             anchor="e")
            for x in range(zone_w):
                on = x < zone_w * pct
                c = (multi_stop(["#8A6D1D", "#F5C542"],
                                x / max(1, zone_w * pct))
                     if pct > 0 and on else "#26333E")
                self.create_line(24 + x, h - 28, 24 + x, h - 28 + bar_h,
                                 fill=c)
        elif wp is not None:
            split = zone_w * wp / 100
            seam = max(6, zone_w // 16)
            for x in range(zone_w):
                if x < split - seam / 2:
                    c = multi_stop(["#2E7D51", WIN], x / max(1, split))
                elif x < split + seam / 2:
                    c = "#3E4A52"
                else:
                    t = (x - split) / max(1, zone_w - split)
                    c = multi_stop([LOSS, "#7A2E36"], min(1.0, t))
                self.create_line(24 + x, h - 28, 24 + x, h - 28 + bar_h,
                                 fill=c)
            self.create_text(24, h - 38, text=f"YOUR TEAM {wp}%", fill=WIN,
                             font=("Segoe UI", 8, "bold"), anchor="w")
            self.create_text(text_right, h - 38, text=f"{100 - wp}%",
                             fill=LOSS, font=("Segoe UI", 8, "bold"),
                             anchor="e")


class AssistantBanner(tk.Frame):
    """Agent-Select banner with the map + pick recommendation (teal left
    strip like the web dashboard). Purely informational."""

    def __init__(self, master, app):
        super().__init__(master, bg=CARD,
                         highlightbackground=TEAL, highlightthickness=1,
                         padx=0, pady=12)
        self.app = app
        self._visible = False
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="x", padx=16)
        self.title_lbl = tk.Label(inner, text="Agent Select", bg=CARD,
                                  fg=TEXT, font=("Segoe UI", 12, "bold"))
        self.title_lbl.pack(anchor="w")
        self.sub_lbl = tk.Label(inner, text="", bg=CARD, fg=TEXT_DIM,
                                font=("Segoe UI", 9), anchor="w",
                                justify="left")
        self.sub_lbl.pack(anchor="w", pady=(4, 0))

        self._actions = None

    def update_board(self, board: dict) -> None:
        ql = board.get("quickLock") or {}
        asst = board.get("assistant") or {}
        state = board.get("state")
        show = state == "PREGAME" and asst.get("enabled")
        if not show:
            self.pack_forget()
            self._visible = False
            return
        self._visible = True
        self.pack(fill="x", pady=(6, 0), before=self.master.hero)
        map_name = asst.get("map") or board.get("map") or ""
        pref = asst.get("preferred") or asst.get("rec")
        meta = asst.get("preferredMeta") or {}
        title = "Agent Select" + (f" — {map_name}" if map_name else "")
        if asst.get("enabled") and pref:
            title += f".  Your pick: {pref}"
            if meta.get("role"):
                title += f"  ({meta['role']})"
        self.title_lbl.configure(text=title)
        bits = []
        if asst.get("preferred") and asst.get("rec") \
                and asst["preferred"] != asst["rec"]:
            bits.append(f"Recommendation from your stats: {asst['rec']}.")
        self.sub_lbl.configure(text=" ".join(bits))
