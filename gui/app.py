"""Valtix GUI — main window."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk

from .theme import (AMBER, BG, BG_RAISED, CARD, GRAD_HEADER, GRAD_RULE,
                   GRAD_SIDEBAR, GRAD_STATUS, LINE, RED, RED_SOFT, TEAL,
                   TEXT, TEXT_DIM, TEXT_FAINT, apply, mix, multi_stop)
from .widgets import AccentRule, GradientFrame, Pill, Toast

from .core import AppCore
from .queue_monitor import QueueMonitor
from .widgets import ImageCache
from .tabs.live_tab import LiveTab
from .tabs.performance_tab import PerformanceTab
from .tabs.encounters_tab import EncountersTab
from .tabs.sessions_tab import SessionsTab
from .tabs.inventory_tab import InventoryTab
from .tabs.display_tab import DisplayTab
from .tabs.crosshair_tab import CrosshairTab
from .dialogs import (SettingsDialog, PrivacyDialog, PlayerProfileDialog,
                     MatchDetailDialog)

POLL_PREGAME = 2.5   # agent select: keep the pick banner snappy
POLL_INGAME = 4.0    # same cadence the web dashboard used while playing
POLL_MENUS = 8.0
POLL_IDLE = 12.0     # client closed / demo: relax (adaptive = fewer wasted polls)

NAV = [("live", "LIVE BOARD", "◉"),
       ("performance", "PERFORMANCE", "▤"),
       ("encounters", "ENCOUNTERS", "⌖"),
       ("sessions", "SESSIONS", "◷"),
       ("inventory", "COLLECTION", "❖"),
       ("crosshair", "CROSSHAIR", "✛"),
       ("display", "DISPLAY", "❂")]


class ValtixApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Valtix — Local Edition")
        self.configure(background=BG)
        self.geometry("1280x820")
        self.minsize(1080, 660)

        # core first: window restore and the art cache both read settings
        self.core = AppCore()
        self._fonts = apply(self)
        self._apply_window_icon()
        self._dark_title_bar()
        saved_geom = ""
        try:
            saved_geom = str(self.core.all_settings().get("windowGeometry") or "")
        except Exception:
            saved_geom = ""
        if saved_geom:
            self.geometry(saved_geom)

        self.toast = Toast(self)
        # Worker threads never touch tkinter directly: they push closures
        # into a queue that a UI-side drain loop runs on the main thread.
        self._ui_q: "queue.Queue[callable]" = queue.Queue()
        self.after(80, self._drain_ui_queue)
        art_dir = os.environ.get("VALTIX_DATA_DIR")
        if not art_dir:
            art_dir = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "backend", "data")
        self.art_cache = ImageCache(
            self, os.path.join(art_dir, "artcache"),
            load_art_fn=lambda: bool(self.core.all_settings().get("loadArt", True)),
            post_fn=self._post_ui)
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._board_sig = ""
        self._shutting = False
        self._tab_cache: dict[str, object] = {}
        self._prev_board_state: str | None = None
        self._queue_monitor = QueueMonitor(self)

        # crosshair overlay engine — owns the click-through windows + hotkeys
        from crosshair_overlay import OverlayEngine
        self.crosshair_engine = OverlayEngine(self, self._post_ui)

        self._build_header()
        self._build_body()
        self._build_statusbar()

        self.core.start_services()
        self.after(500, self._start_crosshair_engine)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda e: self.force_refresh())
        self.start_poll()
        self._queue_monitor.start()
        last_tab = ""
        try:
            last_tab = str(self.core.all_settings().get("lastTab") or "")
        except Exception:
            last_tab = ""
        self.after(300, lambda: self.show_tab(
            last_tab if last_tab in {k for k, _l, _i in NAV} else "live"))
        self.after(600, self._poll_demo_welcome)

    # ── window chrome ──────────────────────────────────────────
    def _resource(self, *parts: str) -> str:
        """Path to a bundled resource (works frozen and from source)."""
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, *parts)

    def _apply_window_icon(self) -> None:
        try:
            self.iconbitmap(self._resource("valtix.ico"))
        except Exception:
            try:
                self.iconphoto(True, tk.PhotoImage(
                    file=self._resource("assets", "valtix-brand-256.png")))
            except Exception:
                pass

    def _dark_title_bar(self) -> None:
        """Windows: render the native title bar in dark mode."""
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())

            def set_attr(attr: int, value: int) -> int:
                v = ctypes.c_int(value)
                return ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
            # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older builds)
            if set_attr(20, 1) != 0:
                set_attr(19, 1)
        except Exception:
            pass

    # ── header ─────────────────────────────────────────────────
    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG_RAISED, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand_wrap = tk.Frame(header, bg=BG_RAISED)
        brand_wrap.pack(side="left", padx=(18, 6))
        tk.Label(brand_wrap, text="V", bg=BG_RAISED, fg=RED,
                 font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(brand_wrap, text="VALTIX", bg=BG_RAISED, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=(2, 0))
        edition = tk.Frame(header, bg=BG_RAISED,
                           highlightbackground=LINE, highlightthickness=1)
        edition.pack(side="left", padx=(8, 0), pady=(4, 0))
        tk.Label(edition, text="LOCAL EDITION", bg=BG_RAISED, fg=TEXT_DIM,
                 font=("Segoe UI", 7, "bold"), padx=8,
                 pady=3).pack()

        self.source_pill = Pill(header, "—", bg="#2A3742", fg=TEXT_DIM,
                                font=("Segoe UI", 8, "bold"))
        self.source_pill.pack(side="left", padx=(14, 6))
        self.state_pill = Pill(header, "—", bg=CARD, fg=TEXT,
                               font=("Segoe UI", 8, "bold"))
        self.state_pill.pack(side="left", padx=2)
        self.no_telemetry = Pill(header, "no telemetry · data stays on this PC",
                                 bg=BG_RAISED, fg=TEXT_FAINT, font=("Segoe UI", 8))
        self.no_telemetry.pack(side="left", padx=10)

        btns = tk.Frame(header, bg=BG_RAISED)
        btns.pack(side="right")
        ttk.Button(btns, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.force_refresh).pack(side="left", padx=4)
        ttk.Button(btns, text="⚙  Settings", style="Ghost.TButton",
                   command=self.open_settings).pack(side="left", padx=4)
        AccentRule(self, colors=["#141F2A", RED, "#141F2A"],
                   height=2).pack(fill="x")

    # ── body: sidebar + tab stack ──────────────────────────────
    def _build_body(self) -> None:
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self._active: str | None = None
        self.nav = tk.Frame(body, bg=BG)
        self.nav.pack(fill="x")
        strip = tk.Frame(self.nav, bg=BG)
        strip.pack(pady=(6, 0))
        self._nav_items: dict[str, tk.Label] = {}
        for key, label, _icon in NAV:
            lbl = tk.Label(strip, text=label, bg=BG, fg=TEXT_DIM,
                           font=("Segoe UI", 9, "bold"), padx=14, pady=4,
                           cursor="hand2")
            lbl.pack(side="left", padx=4)
            lbl.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(fg=RED))
            lbl.bind("<Leave>", lambda e, l=lbl, k=key: l.configure(
                fg=TEXT if self._active == k else TEXT_DIM))
            lbl._key = key
            self._nav_items[key] = lbl
        AccentRule(self.nav, colors=["#141F2A", RED, "#141F2A"],
                   height=2).pack(fill="x")

        self.content = tk.Frame(body, bg=BG)
        self.content.pack(fill="both", expand=True)
        self._tabs: dict[str, tk.Frame] = {}
        # centered content column like the web dashboard
        self.column = tk.Frame(self.content, bg=BG)
        self.column.place(relx=0.5, rely=0, anchor="n", width=1160,
                          relheight=1)

    def _make_tab(self, key: str):
        if key in self._tab_cache:
            return self._tab_cache[key]
        factories = {
            "live": LiveTab,
            "performance": PerformanceTab,
            "encounters": EncountersTab,
            "sessions": SessionsTab,
            "inventory": InventoryTab,
            "crosshair": CrosshairTab,
            "display": DisplayTab,
        }
        tab = factories[key](self.column, self)
        tab.configure(background=BG)
        self._tab_cache[key] = tab
        return tab

    def show_tab(self, key: str) -> None:
        self._active = key
        for k, lbl in self._nav_items.items():
            lbl.configure(fg=TEXT if k == key else TEXT_DIM)
        for k, frame in list(self._tabs.items()):
            if k != key:
                frame.pack_forget()
        tab = self._make_tab(key)
        if key not in self._tabs:
            self._tabs[key] = tab
        tab.pack(fill="both", expand=True)
        on_show = getattr(tab, "on_show", None)
        if on_show:
            on_show()

    # ── status bar ─────────────────────────────────────────────
    def _build_statusbar(self) -> None:
        GradientFrame(self, GRAD_STATUS, direction="h", height=1).pack(
            fill="x", side="bottom")
        footer = tk.Frame(self, bg=BG_RAISED, height=24)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, text="Valtix is 100% local — dashboard, settings, "
                 "history & statistics live on this PC.", bg=BG_RAISED,
                 fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left",
                                                           padx=(14, 0))
        tk.Label(footer, text="|", bg=BG_RAISED, fg=LINE,
                 font=("Segoe UI", 8)).pack(side="left", padx=12)
        tk.Label(footer, text="Riot communication: only your own client "
                 "session, same as the game UI.", bg=BG_RAISED,
                 fg=TEXT_FAINT, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(footer, text="|", bg=BG_RAISED, fg=LINE,
                 font=("Segoe UI", 8)).pack(side="left", padx=12)
        det = tk.Label(footer, text="Automatic agent selection removed — "
                       "details", bg=BG_RAISED, fg=RED_SOFT,
                       font=("Segoe UI", 8), cursor="hand2")
        det.pack(side="left")
        det.bind("<Button-1>", lambda e: PrivacyDialog(self))
        bar = tk.Frame(self, bg=BG_RAISED, height=26)
        bar.pack(fill="x", side="bottom")
        self.status_dot = tk.Label(bar, text="●", bg=BG_RAISED, fg=TEXT_FAINT,
                                   font=("Segoe UI", 8))
        self.status_dot.pack(side="left", padx=(12, 4))
        self.status_lbl = tk.Label(bar, text="Starting…", bg=BG_RAISED,
                                   fg=TEXT_DIM, font=("Segoe UI", 8))
        self.status_lbl.pack(side="left")
        self.queue_lbl = tk.Label(bar, text="", bg=BG_RAISED, fg=TEAL,
                                  font=("Segoe UI", 8, "bold"))
        self.queue_lbl.pack(side="left", padx=(10, 0))
        self.poll_lbl = tk.Label(bar, text="", bg=BG_RAISED, fg=TEXT_FAINT,
                                 font=("Segoe UI", 8))
        self.poll_lbl.pack(side="right", padx=12)
        tk.Label(bar, text=f"v{self.core.health()['appVersion']} · GUI",
                 bg=BG_RAISED, fg=TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(side="right", padx=6)

    # ── polling ────────────────────────────────────────────────
    def start_poll(self) -> None:
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="valtix-poll", daemon=True)
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        while not self._poll_stop.is_set():
            delay = POLL_IDLE
            try:
                board = self.core.live_board()
                self._post_ui(lambda b=board: self._apply_board(b))
                state = (board.get("state") or "OFFLINE").upper()
                delay = {"PREGAME": POLL_PREGAME, "INGAME": POLL_INGAME,
                         "MENUS": POLL_MENUS}.get(state, POLL_IDLE)
            except Exception:
                self._post_ui(self._poll_error)
                delay = POLL_IDLE
            self._poll_stop.wait(delay)

    def _poll_error(self) -> None:
        self.status_lbl.configure(text="Board build failed — check Logs")
        self.status_dot.configure(fg=RED)

    # ── alerts ─────────────────────────────────────────────────
    def notify(self, message: str, *, kind: str = "info",
               sound: bool = False) -> None:
        """Toast + optional sound (respects the soundAlerts setting)."""
        self.toast.show(message, kind=kind)
        if sound:
            try:
                if bool(self.core.all_settings().get("soundAlerts", True)):
                    import winsound
                    flag = winsound.MB_ICONASTERISK if kind in ("info", "ok") \
                        else winsound.MB_ICONEXCLAMATION
                    winsound.MessageBeep(flag)
            except Exception:
                pass

    def _check_state_transition(self, board: dict) -> None:
        """Match-found / match-end alerts from live board state changes."""
        if board.get("source") != "local":
            return
        state = board.get("state")
        prev = self._prev_board_state
        self._prev_board_state = state
        if not state or not prev or state == prev:
            return
        if state == "PREGAME" and prev in ("MENUS", "OFFLINE"):
            self.notify("Match found — agent select is open!",
                        kind="ok", sound=True)
        elif prev == "INGAME" and state in ("MENUS", "PREGAME"):
            self._announce_match_end(board)

    def _announce_match_end(self, board: dict) -> None:
        fs = board.get("finalScoreboard") or {}
        result = fs.get("result")
        scores = fs.get("scores") or {}
        self_team = fs.get("selfTeam") or board.get("selfTeam") or "Blue"
        other = next((t for t in scores if t != self_team), None)
        score = (f"{scores.get(self_team, '?')}–{scores.get(other, '?')}"
                 if other is not None else "")
        kind = "ok" if result == "Victory" else "warn"
        base = f"{result or 'Match ended'} {score}".strip()
        self.notify(base + " — checking RR…", kind=kind, sound=True)

        def work():
            perf = self.core.performance()
            points = perf.get("points") or []
            for p in reversed(points):
                if isinstance(p.get("delta"), (int, float)):
                    return p.get("delta"), p.get("tier")
            return None, None

        def done(args):
            delta, _tier = args
            if delta is not None:
                sign = "+" if delta > 0 else ""
                self.toast.show(f"{base}  ·  {sign}{delta} RR", kind=kind)

        self.run_bg(work, done)

    def _apply_board(self, board: dict) -> None:
        if self._shutting:
            return
        self._check_state_transition(board)
        sig = json.dumps(board, default=str, sort_keys=True)
        volatile = {"riotRequests", "appVersion"}
        # recompute signature without volatile keys (cheap enough at these sizes)
        trimmed = {k: v for k, v in board.items() if k not in volatile}
        sig = json.dumps(trimmed, default=str, sort_keys=True)
        source = board.get("source", "demo")
        live = source == "local"
        self.source_pill.configure(
            text="LIVE · LOCAL CLIENT" if live else "DEMO DATA",
            bg="#153A31" if live else "#33262A",
            fg=TEAL if live else RED_SOFT)
        self.state_pill.configure(
            text=(board.get("stateLabel") or board.get("state") or "—").upper())
        client_status = "VALORANT client: connected" if live else \
            "VALORANT client: not running — showing demo data"
        self.status_lbl.configure(text=client_status)
        self.status_dot.configure(fg=TEAL if live else AMBER)
        state = (board.get("state") or "OFFLINE").upper()
        cadence = {"PREGAME": POLL_PREGAME, "INGAME": POLL_INGAME,
                   "MENUS": POLL_MENUS}.get(state, POLL_IDLE)
        self.poll_lbl.configure(text=f"auto-poll {cadence:.0f}s")
        if sig != self._board_sig:
            self._board_sig = sig
        live_tab = self._tab_cache.get("live")
        if live_tab:
            live_tab.update_board(board)

    def _poll_demo_welcome(self) -> None:
        if not self._tab_cache.get("live"):
            return
        if self.core.client.source_pref == "demo":
            self.toast.show("Running in demo mode — open VALORANT to go live.",
                            kind="info")

    # ── thread → UI bridge ─────────────────────────────────────
    def _post_ui(self, fn) -> None:
        """Thread-safe: queue a callable to run on the UI thread."""
        self._ui_q.put(fn)

    def _drain_ui_queue(self) -> None:
        if self._shutting:
            return
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    traceback.print_exc(limit=3)
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    # ── background task runner ─────────────────────────────────
    def run_bg(self, fn, on_done, on_error=None) -> None:
        def work():
            try:
                result = fn()
            except Exception:
                err = traceback.format_exc(limit=3)
                self._post_ui(lambda: (on_error(err) if on_error
                                       else self.toast.show(
                                           f"Error: {err.splitlines()[-1]}",
                                           kind="error")))
                return
            self._post_ui(lambda: on_done(result))
        threading.Thread(target=work, daemon=True).start()

    # ── actions ────────────────────────────────────────────────
    def force_refresh(self) -> None:
        self._board_sig = ""

        def refresh():
            return self.core.refresh_now()

        def done(_board):
            self.toast.show("Refreshed", ms=1200, kind="ok")
        self.run_bg(refresh, done)

    def open_settings(self) -> None:
        SettingsDialog(self)

    def open_privacy(self) -> None:
        PrivacyDialog(self)

    def quit_app(self) -> None:
        self._on_close()

    # ── shutdown ───────────────────────────────────────────────
    def _start_crosshair_engine(self) -> None:
        """Boot the crosshair overlay once the main window is up."""
        try:
            self.crosshair_engine.start()
        except Exception:
            traceback.print_exc()

    def _on_close(self) -> None:
        if self._shutting:
            self.destroy()
            return
        self._shutting = True
        self._poll_stop.set()
        self._queue_monitor.stop()
        try:
            self.crosshair_engine.stop()
        except Exception:
            pass
        try:
            geom = f"{self.winfo_width()}x{self.winfo_height()}"
            self.core.update_settings({
                "windowGeometry": geom,
                "lastTab": self._active or "",
            })
        except Exception:
            pass
        self.core.stop_services()
        for tab in self._tab_cache.values():
            shutdown = getattr(tab, "shutdown", None)
            if shutdown:
                shutdown()
        self.destroy()


class SidebarCanvas(tk.Canvas):
    """Gradient sidebar with icon nav, hover glow and a red active bar."""

    ROW_H = 46
    TOP_PAD = 18

    def __init__(self, master, app, items):
        super().__init__(master, width=190, highlightthickness=0, bd=0,
                         bg=BG_RAISED)
        self.app = app
        self._items = items
        self._active: str | None = None
        self._hover: str | None = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)

    def _row_rect(self, i: int) -> tuple[int, int]:
        y = self.TOP_PAD + i * self.ROW_H
        return y, y + self.ROW_H - 8

    def set_active(self, key: str | None) -> None:
        self._active = key
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width() or 190
        h = self.winfo_height() or 600
        for y in range(h):
            self.create_line(0, y, w, y,
                             fill=multi_stop(GRAD_SIDEBAR, y / max(1, h - 1)))
        self.create_line(w - 1, 0, w - 1, h, fill="#0B1218")
        for i, (key, label, icon) in enumerate(self._items):
            y0, y1 = self._row_rect(i)
            active = key == self._active
            hovered = key == self._hover
            if active:
                self.create_rectangle(12, y0, w - 10, y1,
                                      fill=mix("#101B24", RED, 0.10),
                                      outline="")
                self.create_rectangle(0, y0 + 1, 3, y1 - 1, fill=RED,
                                      outline="")
            fg = RED if active else (TEXT if hovered else TEXT_DIM)
            ico_fg = RED if active else (TEXT_DIM if hovered else TEXT_FAINT)
            cy = (y0 + y1) // 2
            self.create_text(24, cy, text=icon, fill=ico_fg,
                             font=("Segoe UI", 10), anchor="w")
            self.create_text(52, cy, text=label, fill=fg,
                             font=("Segoe UI", 9, "bold"), anchor="w")

    def _row_at(self, y: int) -> str | None:
        for i, (key, _l, _i) in enumerate(self._items):
            y0, y1 = self._row_rect(i)
            if y0 <= self.canvasy(y) <= y1:
                return key
        return None

    def _on_motion(self, evt) -> None:
        self._set_hover(self._row_at(evt.y))

    def _set_hover(self, key: str | None) -> None:
        if key != self._hover:
            self._hover = key
            self.configure(cursor="hand2" if key else "")
            self.redraw()

    def _on_click(self, evt) -> None:
        key = self._row_at(evt.y)
        if key:
            self.app.show_tab(key)


def run() -> None:
    app = ValtixApp()
    app.mainloop()
