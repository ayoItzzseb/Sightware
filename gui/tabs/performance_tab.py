"""Sightware GUI — Performance tab (RR history, insights, splits, matches)."""
from __future__ import annotations

import time

import tkinter as tk
from tkinter import ttk

from ..theme import (AMBER, BG, CARD, LINE, ORANGE, RED, TEAL, TEXT, TEXT_DIM,
                   TEXT_FAINT, WIN, LOSS, mix)
from ..widgets import (Banner, CalendarHeatmap, DataTable, Column, MiniProgress,
                     RRChart, ScrollFrame, Sparkline, StatCard, section_title)

from ..dialogs import MatchDetailDialog, PlayerProfileDialog


def _ts(ts) -> str:
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(int(ts)))
    except (TypeError, ValueError, OSError):
        return "—"


class PerformanceTab(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.core = app.core
        self._payload: dict | None = None
        self._loaded_once = False
        self._account_filter: str | None = None

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(top, text="ACCOUNT", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.account_cb = ttk.Combobox(top, state="readonly", width=34)
        self.account_cb.pack(side="left", padx=(8, 6))
        self.account_cb.bind("<<ComboboxSelected>>", self._on_account)
        ttk.Button(top, text="⟳", style="Ghost.TButton", width=3,
                   command=self.refresh).pack(side="left", padx=2)
        self.refreshing_lbl = tk.Label(top, text="", bg=BG, fg=TEAL,
                                       font=("Segoe UI", 8))
        self.refreshing_lbl.pack(side="left", padx=8)

        lookup = tk.Frame(top, bg=BG)
        lookup.pack(side="right")
        tk.Label(lookup, text="TIMEZONE", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
        self.tz_cb = ttk.Combobox(lookup, state="readonly", width=22,
                                  values=self._tz_names())
        self.tz_cb.set("UTC (default)")
        self.tz_cb.pack(side="left", padx=(0, 10))
        self.tz_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        tk.Label(lookup, text="PLAYER LOOKUP (PUUID)", bg=BG, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))
        self.lookup_var = tk.StringVar()
        ttk.Entry(lookup, textvariable=self.lookup_var, width=34).pack(side="left")
        ttk.Button(lookup, text="Look up", style="Ghost.TButton",
                   command=self._lookup).pack(side="left", padx=(6, 0))

        self.scroll = ScrollFrame(self, bg=BG)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner
        self.body = body

        # ── overview section ──
        ov = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                      highlightthickness=1)
        ov.pack(fill="x", padx=16, pady=(10, 8))
        tk.Label(ov, text="OVERVIEW", bg=CARD, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14,
                                                    pady=(10, 4))
        # summary cards
        cards = tk.Frame(ov, bg=CARD)
        cards.pack(fill="x", padx=14, pady=(0, 4))
        self.c_rank = StatCard(cards, "current rank")
        self.c_wr = StatCard(cards, "win rate")
        self.c_matches = StatCard(cards, "matches")
        self.c_net = StatCard(cards, "net rr")
        self.c_best = StatCard(cards, "best acs")
        self.c_streak = StatCard(cards, "avg win / loss")
        for c in (self.c_rank, self.c_wr, self.c_matches,
                  self.c_net, self.c_best, self.c_streak):
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.trend_wrap = tk.Frame(ov, bg=CARD)
        self.trend_wrap.pack(fill="x", padx=14, pady=(6, 10))
        tk.Label(self.trend_wrap, text="TRENDS - last 20 ranked matches",
                 bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8, "bold")
                 ).pack(anchor="w")
        trend_row = tk.Frame(self.trend_wrap, bg=BG)
        trend_row.pack(fill="x")
        self.trend_kd = Sparkline(trend_row, label="K/D")
        self.trend_acs = Sparkline(trend_row, label="ACS")
        self.trend_rr = Sparkline(trend_row, label="RR delta")
        for sp in (self.trend_kd, self.trend_acs, self.trend_rr):
            sp.pack(side="left", padx=(0, 10), fill="x", expand=True)

        prog = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1)
        prog.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(prog, text="RANK PROGRESSION", bg=CARD, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14,
                                                    pady=(10, 4))
        self.next_wrap = tk.Frame(prog, bg=CARD)
        self.next_lbl = tk.Label(self.next_wrap, text="", bg=CARD, fg=TEXT_DIM,
                                 font=("Segoe UI", 9))
        self.next_lbl.pack(anchor="w", padx=2, pady=(2, 2))
        self.next_bar = MiniProgress(self.next_wrap, height=5, color=RED)
        self.next_bar.pack(fill="x", padx=1)
        self.next_wrap.pack(fill="x", padx=14, pady=(0, 8))
        self.prog_card = prog

        # RR chart
        section_title(body, "match history (RR per game)").pack(
            anchor="w", padx=16, pady=(10, 4))
        self.chart = RRChart(body)
        self.chart.pack(fill="x", padx=16)

        # insights
        self.insights_wrap = tk.Frame(body, bg=BG)
        self.insights_wrap.pack(fill="x", padx=16, pady=(10, 0))

        # splits
        splits = tk.Frame(body, bg=BG)
        splits.pack(fill="x", padx=16, pady=(12, 0))
        left = tk.Frame(splits, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(splits, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        section_title(left, "by agent").pack(anchor="w", pady=(0, 4))
        self.agent_table = DataTable(left, [
            Column("name", "Agent", 110),
            Column("games", "Games", 60, "e"),
            Column("winRate", "WR%", 56, "e"),
            Column("netRr", "Net RR", 66, "e"),
            Column("avgKd", "K/D", 50, "e"),
            Column("avgAcs", "ACS", 56, "e"),
        ], height=170, row_h=26)
        self.agent_table.pack(fill="x")
        section_title(right, "by map").pack(anchor="w", pady=(0, 4))
        self.map_table = DataTable(right, [
            Column("name", "Map", 110),
            Column("games", "Games", 60, "e"),
            Column("winRate", "WR%", 56, "e"),
            Column("netRr", "Net RR", 66, "e"),
            Column("avgKd", "K/D", 50, "e"),
            Column("avgAcs", "ACS", 56, "e"),
        ], height=170, row_h=26)
        self.map_table.pack(fill="x")

        cal = tk.Frame(body, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1)
        cal.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(cal, text="PLAY CALENDAR - click a day to see every match",
                 bg=CARD, fg=TEXT_FAINT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14,
                                                    pady=(10, 4))
        nav = tk.Frame(cal, bg=CARD)
        nav.pack(fill="x", padx=14, pady=(0, 4))
        ttk.Button(nav, text="◀", style="Ghost.TButton", width=3,
                   command=lambda: self._step_month(-1)).pack(side="left")
        self.month_cb = ttk.Combobox(nav, state="readonly", width=16)
        self.month_cb.pack(side="left", padx=6)
        self.month_cb.bind("<<ComboboxSelected>>", self._on_month_selected)
        ttk.Button(nav, text="▶", style="Ghost.TButton", width=3,
                   command=lambda: self._step_month(1)).pack(side="left")
        self.heatmap = CalendarHeatmap(cal, height=186,
                                       on_click=self._open_day)
        self.heatmap.pack(fill="x", padx=14)
        legend = tk.Frame(cal, bg=CARD)
        legend.pack(anchor="w", padx=14, pady=(6, 0))
        tk.Label(legend, text="fewer games", bg=CARD, fg=TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(side="left")
        for col in ("#1A2530", mix("#1A2530", LOSS, 0.5), mix("#1A2530", WIN, 0.3),
                    mix("#1A2530", WIN, 0.6), mix("#1A2530", WIN, 0.9)):
            tk.Label(legend, text="   ", bg=col,
                     highlightbackground=LINE, highlightthickness=1
                     ).pack(side="left", padx=1)
        tk.Label(legend, text="more games · green = won RR · red = lost RR",
                 bg=CARD, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left",
                                                                    padx=4)
        self.heatmap_info = tk.Label(cal, text="hover a day for a summary",
                                     bg=CARD, fg=TEXT_FAINT, font=("Segoe UI", 8))
        self.heatmap_info.pack(anchor="w", padx=16, pady=(2, 10))
        self.heatmap._on_hover = self._heatmap_hover
        if months_avail := self.heatmap.months_available():
            self.heatmap.set_month(months_avail[-1])
        self._refresh_month_nav()

        section_title(body, "schedule").pack(anchor="w", padx=16, pady=(12, 4))
        self.schedule_table = DataTable(body, [
            Column("name", "When", 110),
            Column("games", "Games", 70, "e"),
            Column("wins", "W", 50, "e"),
            Column("winRate", "WR%", 60, "e"),
            Column("netRr", "Net RR", 70, "e"),
        ], height=210, row_h=24)
        self.schedule_table.pack(fill="x", padx=16)

        # rank changes
        section_title(body, "rank changes").pack(anchor="w", padx=16,
                                                 pady=(12, 4))
        self.changes_table = DataTable(body, [
            Column("ts", "Date", 110),
            Column("type", "Type", 100),
            Column("fromRank", "From", 120),
            Column("toRank", "To", 120),
        ], height=140, row_h=24)
        self.changes_table.pack(fill="x", padx=16)

        # match list
        match_head = tk.Frame(body, bg=BG)
        match_head.pack(fill="x", padx=16, pady=(12, 4))
        section_title(match_head, "matches").pack(side="left")
        ttk.Button(match_head, text="Export CSV", style="Ghost.TButton",
                   command=self._export_matches_csv).pack(side="right")
        tk.Label(match_head, text="click a row for the full match report",
                 bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left", padx=8)
        self.match_table = DataTable(body, [
            Column("date", "Date", 96),
            Column("result", "Result", 76),
            Column("delta", "RR", 52, "e"),
            Column("agent", "Agent", 96),
            Column("map", "Map", 96),
            Column("kd", "K/D", 52, "e"),
            Column("acs", "ACS", 56, "e"),
            Column("note", "Note / tags", 240, stretch=True),
        ], height=280, row_h=26, on_row_click=self._open_match)
        self.match_table.pack(fill="x", padx=16, pady=(0, 12))

        self.loading = tk.Label(body, text="Loading performance…", bg=BG,
                                fg=TEXT_DIM, font=("Segoe UI", 9))
        self.loading.pack(pady=24)

    @staticmethod
    def _tz_names() -> list[str]:
        try:
            from zoneinfo import available_timezones
            zones = sorted(z for z in available_timezones() if "/" in z)
            return ["UTC (default)"] + zones
        except Exception:
            return ["UTC (default)"]

    def _tz_value(self) -> str | None:
        sel = self.tz_cb.get()
        return None if sel in ("", "UTC (default)") else sel

    # ── data ───────────────────────────────────────────────────
    def on_show(self) -> None:
        if not self._loaded_once:
            self.refresh()

    def refresh(self) -> None:
        account = self._account_filter
        tz = self._tz_value() if hasattr(self, "tz_cb") else None

        def work():
            return self.core.performance(timezone_name=tz,
                                         account_puuid=account)

        self.loading.configure(text="Loading performance…")
        self.app.run_bg(work, self._apply, self._error)

    def _on_account(self, _evt=None) -> None:
        selection = self.account_cb.current()
        accounts = (self._payload or {}).get("accounts") or []
        if 0 <= selection < len(accounts):
            self._account_filter = accounts[selection].get("puuid")
            self.refresh()

    def _lookup(self) -> None:
        puuid = self.lookup_var.get().strip()
        if not puuid:
            return
        PlayerProfileDialog(self.app, puuid)

    def _error(self, err: str) -> None:
        self.loading.configure(text=f"Failed to load: {err.splitlines()[-1]}")

    def _apply(self, payload: dict) -> None:
        self._last_payload = payload
        if payload.get("error"):
            self.loading.configure(text=payload["error"])
            return
        self._loaded_once = True
        self._payload = payload
        self.loading.pack_forget()
        self._render_accounts(payload)
        self._render_summary(payload)
        self.chart.set_points(payload.get("points") or [])
        self._render_insights(payload.get("insights") or [])
        self._render_splits(payload)
        self._render_changes(payload)
        self._render_matches(payload)

    def _render_accounts(self, payload: dict) -> None:
        accounts = payload.get("accounts") or []
        names = []
        for a in accounts:
            name = a.get("riotId") or (a.get("puuid") or "")[:8]
            tag = " (current)" if a.get("puuid") == payload.get("currentAccountPuuid") else ""
            names.append(f"{name}{tag}")
        self.account_cb.configure(values=names)
        current = payload.get("account") or {}
        puuid = current.get("puuid")
        idx = next((i for i, a in enumerate(accounts) if a.get("puuid") == puuid), 0)
        if names:
            self.account_cb.current(min(idx, len(names) - 1))
        self.refreshing_lbl.configure(
            text="refreshing in background…" if payload.get("refreshing") else "")

    def _render_summary(self, payload: dict) -> None:
        s = payload.get("summary") or {}
        current = s.get("current") or {}
        self.c_rank.set(current.get("name", "—"),
                        sub=f"{current.get('rr') or 0} RR",
                        color=current.get("color") or TEXT)
        wr = s.get("winRate")
        self.c_wr.set(f"{wr}%" if wr is not None else "—",
                      sub=f"{s.get('wins', 0)}W · {s.get('losses', 0)}L",
                      color=WIN if (wr or 0) >= 50 else TEXT)
        self.c_matches.set(str(s.get("matches", 0)), sub="ranked matches")
        net = s.get("net") or 0
        self.c_net.set(f"{'+' if net > 0 else ''}{net}", sub="RR across matches",
                       color=WIN if net > 0 else LOSS if net < 0 else TEXT)
        best = payload.get("personalBests") or {}
        self.c_best.set(str(best.get("bestAcs") or "—"), sub="personal best")
        avg_w, avg_l = s.get("avgWin"), s.get("avgLoss")
        self.c_streak.set(
            f"{avg_w if avg_w is not None else '—'} / {avg_l if avg_l is not None else '—'}",
            sub="avg win / avg loss RR",
            color=WIN if (avg_w or 0) > abs(avg_l or 0) else TEXT)

        nxt = s.get("next")
        if nxt:
            self.next_wrap.pack(fill="x", padx=16, pady=(0, 8))
            self.next_lbl.configure(
                text=f"Next rank: {nxt.get('name')} — {nxt.get('rrNeeded', 0)} RR to go")
            self.next_bar.set(nxt.get("progress", 0))
            self._render_projection(payload, nxt)
        else:
            self.next_wrap.pack_forget()
        self._render_trends(payload)
        self._render_map_picks(payload)

    def _render_projection(self, payload, nxt):
        points = [p for p in (payload.get("points") or []) if p.get("delta") is not None]
        if len(points) < 5 or not nxt:
            return
        deltas = [p["delta"] for p in points[-20:]]
        avg = sum(deltas) / len(deltas)
        needed = nxt.get("rrNeeded", 0) or 0
        if avg <= 0:
            text = (f"Projection: {nxt.get('name')} needs {needed} more RR — "
                    f"you are averaging {avg:+.1f} RR/match over your last "
                    f"{len(deltas)}.")
        else:
            games = max(1, round(needed / avg))
            text = (f"Projection: {nxt.get('name')} in ~{games} matches at your "
                    f"current pace ({avg:+.1f} RR/match over {len(deltas)} games).")
        if not hasattr(self, "_proj_banner"):
            self._proj_banner = Banner(self.prog_card, "", "info")
        self._proj_banner.set(text)
        self._proj_banner.pack(fill="x", padx=14, pady=(0, 10))

    def _render_trends(self, payload):
        pts = (payload.get("points") or [])[-20:]
        kd = [p["kd"] for p in pts if p.get("kd") is not None]
        acs = [p["acs"] for p in pts if p.get("acs") is not None]
        rr = [p["delta"] for p in pts if p.get("delta") is not None]
        self.trend_kd.set_values(kd)
        self.trend_acs.set_values(acs)
        self.trend_rr.set_values(rr)

    def _render_map_picks(self, payload):
        """Per-map agent recommendation computed from match history."""
        agg = {}
        for p in (payload.get("points") or []):
            map_name, agent = p.get("map"), p.get("agent")
            if not map_name or not agent:
                continue
            slot = agg.setdefault(map_name, {}).setdefault(agent, [0, 0])
            slot[1] += 1
            if p.get("result") == "Victory":
                slot[0] += 1
        picks = []
        for map_name, agents in agg.items():
            rated = [(wins / g, g, agent) for agent, (wins, g) in agents.items()
                     if g >= 3]
            if rated:
                rated.sort(reverse=True)
                wr, g, agent = rated[0]
                picks.append(f"{map_name}: {agent} ({round(wr * 100)}% WR, {g} games)")
        if not hasattr(self, "_picks_banner"):
            self._picks_banner = Banner(self.prog_card, "", "info")
        if picks:
            self._picks_banner.set("Best agents by map — " + "  ·  ".join(picks[:6]))
            self._picks_banner.pack(fill="x", padx=14, pady=(0, 10))
        elif hasattr(self, "_picks_banner"):
            self._picks_banner.pack_forget()

    def _export_matches_csv(self):
        from tkinter import filedialog
        dest = filedialog.asksaveasfilename(
            title="Export matches as CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        import csv as csvmod
        payload = getattr(self, "_last_payload", None) or {}
        meta = payload.get("matchMeta") or {}
        rows = []
        for p in reversed((payload.get("points") or [])):
            m = meta.get(p.get("matchId") or "") or {}
            rows.append({
                "date": _ts(p.get("ts")),
                "result": p.get("result") or "",
                "rrDelta": p.get("delta"),
                "agent": p.get("agent") or "",
                "map": p.get("map") or "",
                "kd": p.get("kd"),
                "acs": p.get("acs"),
                "note": m.get("note") or "",
            })
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csvmod.DictWriter(f, fieldnames=["date", "result", "rrDelta",
                                                 "agent", "map", "kd", "acs", "note"])
            w.writeheader()
            w.writerows(rows)
        self.app.toast.show(f"Exported {len(rows)} matches to CSV.", kind="ok")

    def _render_insights(self, insights: list[dict]) -> None:
        for child in self.insights_wrap.winfo_children():
            child.destroy()
        if not insights:
            return
        section_title(self.insights_wrap, "insights").pack(anchor="w",
                                                           pady=(0, 4))
        for ins in insights[:6]:
            tone = ins.get("tone", "neutral")
            color = {"positive": TEAL, "negative": LOSS,
                     "warning": AMBER}.get(tone, TEXT_DIM)
            row = Banner(self.insights_wrap,
                         f"{ins.get('title', '')} — {ins.get('text', '')}",
                         "info")
            row.strip.configure(bg=color)
            row.pack(fill="x", pady=2)

    def _render_splits(self, payload: dict) -> None:
        sched = (payload.get("splits") or {}).get("schedule") or {}
        self.heatmap.set_days(sched.get("calendar") or [])

        def rows_of(items):
            rows = []
            for it in items or []:
                rows.append({
                    "cells": {
                        "name": it.get("name", "—"),
                        "games": str(it.get("games", 0)),
                        "winRate": f"{it.get('winRate', 0)}%",
                        "netRr": f"{'+' if (it.get('netRr') or 0) > 0 else ''}{it.get('netRr', 0)}",
                        "avgKd": str(it.get("avgKd") if it.get("avgKd") is not None else "—"),
                        "avgAcs": str(it.get("avgAcs") if it.get("avgAcs") is not None else "—"),
                    },
                    "colors": {
                        "winRate": WIN if (it.get("winRate") or 0) >= 50 else LOSS,
                        "netRr": WIN if (it.get("netRr") or 0) > 0
                                 else LOSS if (it.get("netRr") or 0) < 0 else TEXT,
                    },
                    "data": {"kind": "split", "name": it.get("name")},
                })
            return rows
        self.agent_table.set_rows(rows_of((payload.get("splits") or {}).get("agents")))
        self.map_table.set_rows(rows_of((payload.get("splits") or {}).get("maps")))

        # the calendar's data lands here — pick the latest month on first load
        if getattr(self.heatmap, "_month", None) is None:
            months = self.heatmap.months_available()
            if months:
                self.heatmap.set_month(months[-1])
        self._refresh_month_nav()

        srows = []
        for row in (sched.get("weekdays") or []) + (sched.get("dayparts") or []):
            if not row.get("games"):
                continue
            srows.append({
                "cells": {
                    "name": row.get("name", "—"),
                    "games": str(row.get("games", 0)),
                    "wins": str(row.get("wins", 0)),
                    "winRate": f"{row.get('winRate')}%" if row.get("winRate") is not None else "—",
                    "netRr": f"{'+' if (row.get('netRr') or 0) > 0 else ''}{row.get('netRr', 0)}",
                },
                "colors": {
                    "winRate": WIN if (row.get("winRate") or 0) >= 50 else LOSS,
                },
            })
        self.schedule_table.set_rows(srows)

    def _open_day(self, day: dict) -> None:
        day_name = day.get("name", "")
        matches = self._matches_for_day(day_name)
        DayDetailsDialog(self.app, day, matches)

    def _matches_for_day(self, day_name: str) -> list[dict]:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        payload = self._last_payload or {}
        tz = self._tz_value()
        zone = None
        if tz:
            try:
                zone = ZoneInfo(tz)
            except Exception:
                zone = None
        out = []
        for p in (payload.get("points") or []):
            ts = p.get("ts")
            if not ts:
                continue
            local = (datetime.fromtimestamp(ts, zone) if zone
                     else datetime.fromtimestamp(ts))
            if local.strftime("%Y-%m-%d") == day_name:
                out.append({**p, "_time": local.strftime("%H:%M")})
        out.sort(key=lambda m: m.get("ts") or 0)
        return out

    def _refresh_month_nav(self) -> None:
        months = self.heatmap.months_available()
        if not months:
            self.month_cb.configure(values=[])
            self.month_cb.set("—")
            return
        import datetime as _dt
        labels = []
        for ym in months:
            y, m = (int(x) for x in ym.split("-"))
            labels.append(_dt.date(y, m, 1).strftime("%B %Y"))
        self.month_cb.configure(values=labels)
        current = getattr(self.heatmap, "_month", None) or months[-1]
        if current not in months:
            current = months[-1]
            self.heatmap.set_month(current)
        self.month_cb.set(labels[months.index(current)])

    def _step_month(self, delta: int) -> None:
        current = self.heatmap.step_month(delta)
        if current:
            self._refresh_month_nav()

    def _on_month_selected(self, _e=None) -> None:
        import datetime as _dt
        label = self.month_cb.get()
        months = self.heatmap.months_available()
        for ym in months:
            y, m = (int(x) for x in ym.split("-"))
            if _dt.date(y, m, 1).strftime("%B %Y") == label:
                self.heatmap.set_month(ym)
                return

    def _heatmap_hover(self, text: str | None) -> None:
        self.heatmap_info.configure(text=text or "hover a day for details",
                                    fg=TEXT_DIM if text else TEXT_FAINT)

    def _render_changes(self, payload: dict) -> None:
        from vconstants import rank_from_tier
        rows = []
        for ch in (payload.get("rankChanges") or [])[-12:][::-1]:
            frm = rank_from_tier(ch.get("fromTier"))
            to = rank_from_tier(ch.get("toTier"))
            promotion = ch.get("type") == "promotion"
            rows.append({
                "cells": {
                    "ts": _ts(ch.get("ts")),
                    "type": "▲ Promotion" if promotion else "▼ Demotion",
                    "fromRank": frm["name"],
                    "toRank": to["name"],
                },
                "colors": {
                    "type": TEAL if promotion else LOSS,
                    "fromRank": frm["color"],
                    "toRank": to["color"],
                },
            })
        self.changes_table.set_rows(rows)

    def _render_matches(self, payload: dict) -> None:
        meta = payload.get("matchMeta") or {}
        rows = []
        for p in reversed((payload.get("points") or [])[-60:]):
            result = p.get("result")
            delta = p.get("delta")
            m = meta.get(p.get("matchId") or "")
            note = (m or {}).get("note") or ""
            tags = ", ".join((m or {}).get("tags") or [])
            label = " · ".join(x for x in (note, tags) if x)
            if (m or {}).get("bookmarked"):
                label = ("★ " + label).strip()
            rows.append({
                "cells": {
                    "date": _ts(p.get("ts")),
                    "result": result or "—",
                    "delta": f"{'+' if (delta or 0) > 0 else ''}{delta if delta is not None else '—'}",
                    "agent": p.get("agent") or "—",
                    "map": p.get("map") or "—",
                    "kd": str(p.get("kd")) if p.get("kd") is not None else "—",
                    "acs": str(p.get("acs")) if p.get("acs") is not None else "—",
                    "note": label,
                },
                "colors": {
                    "result": WIN if result == "Victory"
                              else LOSS if result == "Defeat" else TEXT_DIM,
                    "delta": WIN if (delta or 0) > 0
                             else LOSS if (delta or 0) < 0 else TEXT_DIM,
                },
                "accent": RED if (m or {}).get("bookmarked") else None,
                "data": {"kind": "match", "matchId": p.get("matchId"),
                         "subject": payload.get("account", {}).get("puuid")},
            })
        self.match_table.set_rows(rows)

    def _open_match(self, data: dict) -> None:
        if not data.get("matchId"):
            return
        MatchDetailDialog(self.app, data["matchId"], subject=data.get("subject"))


class DayDetailsDialog(tk.Toplevel):
    """Everything recorded about one calendar day: summary chips plus a
    clickable list of every match played (opens the full match report)."""

    def __init__(self, app, day: dict, matches: list[dict]):
        super().__init__()
        self.app = app
        day_name = day.get("name", "?")
        self.title(f"Day details - {day_name}")
        self.configure(bg=BG)
        self.transient(app.winfo_toplevel())
        dlg_w, dlg_h = 720, 620
        self.geometry(f"{dlg_w}x{dlg_h}+{max(0, app.winfo_rootx() + 180)}+"
                      f"{max(0, app.winfo_rooty() + 60)}")
        self.grab_set()

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(head, text=day_name, bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(side="left")
        wins = int(day.get("wins") or 0)
        games = int(day.get("games") or 0)
        net = int(day.get("netRr") or 0)
        wr = day.get("winRate")
        chips = tk.Frame(self, bg=BG)
        chips.pack(fill="x", padx=18, pady=(4, 10))

        def chip(label, value, color=TEXT):
            box = tk.Frame(chips, bg=CARD, highlightbackground=LINE,
                           highlightthickness=1, padx=14, pady=8)
            box.pack(side="left", padx=(0, 8))
            tk.Label(box, text=value, bg=CARD, fg=color,
                     font=("Segoe UI", 13, "bold")).pack(anchor="w")
            tk.Label(box, text=label, bg=CARD, fg=TEXT_FAINT,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
        chip("games", str(games))
        chip("record", f"{wins}W - {games - wins}L",
             WIN if wins * 2 >= games else LOSS if wins else TEXT)
        chip("win rate", f"{wr}%" if wr is not None else "—")
        chip("net RR", f"{'+' if net > 0 else ''}{net}",
             WIN if net > 0 else LOSS if net < 0 else TEXT)

        tk.Label(self, text="EVERY MATCH - click one for the full report "
                            "(all players, rounds, ACS...)", bg=BG,
                 fg=TEXT_FAINT, font=("Segoe UI", 8, "bold")
                 ).pack(anchor="w", padx=18, pady=(6, 4))

        if not matches:
            tk.Label(self, text="No matches recorded for this day.",
                     bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 9)).pack(pady=20)
            return

        columns = [
            Column("time", "Time", 70, "e"),
            Column("map", "Map", 130),
            Column("agent", "Agent", 110),
            Column("result", "Result", 90),
            Column("delta", "RR", 60, "e"),
            Column("kd", "K/D", 60, "e"),
            Column("acs", "ACS", 60, "e"),
        ]
        rows = []
        for m in matches:
            result = m.get("result") or "—"
            delta = m.get("delta")
            rows.append({
                "cells": {
                    "time": m.get("_time", "—"),
                    "map": m.get("map") or "—",
                    "agent": m.get("agent") or "—",
                    "result": result,
                    "delta": f"{'+' if (delta or 0) > 0 else ''}"
                             f"{delta if delta is not None else '—'}",
                    "kd": str(m.get("kd")) if m.get("kd") is not None else "—",
                    "acs": str(m.get("acs")) if m.get("acs") is not None else "—",
                },
                "colors": {
                    "result": WIN if result == "Victory"
                              else LOSS if result == "Defeat" else TEXT_DIM,
                    "delta": WIN if (delta or 0) > 0
                             else LOSS if (delta or 0) < 0 else TEXT_DIM,
                },
                "data": {"kind": "match", "matchId": m.get("matchId"),
                         "subject": None},
            })
        table = DataTable(self, columns, height=max(160, 30 * len(rows)),
                          row_h=26, on_row_click=self._open_match)
        table.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        table.set_rows(rows)
        tk.Label(self, text=f"{len(matches)} matches · {wins}W-{games - wins}L "
                            f"· {net:+d} RR across the day",
                 bg=BG, fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(anchor="w",
                                                                  padx=18,
                                                                  pady=(0, 12))

    def _open_match(self, data: dict) -> None:
        if data.get("matchId"):
            MatchDetailDialog(self.app, data["matchId"],
                              subject=data.get("subject"))
