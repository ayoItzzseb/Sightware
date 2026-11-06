"""Sightware GUI — main window."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk

from .theme import (AMBER, BG, BG_RAISED, CARD, CARD_HI, GRAD_HEADER,
                   GRAD_RULE, GRAD_SIDEBAR, GRAD_STATUS, LINE, LINE_SOFT,
                   PURPLE, RED, RED_SOFT, TEAL, TEXT, TEXT_DIM, TEXT_FAINT,
                   apply, mix, multi_stop, shade)
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

POLL_PREGAME = 1.2   # agent select: locks must appear fast
POLL_INGAME = 4.0    # same cadence the web dashboard used while playing
POLL_MENUS = 8.0
POLL_IDLE = 12.0     # client closed / demo: relax (adaptive = fewer wasted polls)

def _library_names():
    try:
        import crosshair_store as store
        return [p["name"] for p in store.library_list()]
    except Exception:
        return []


NAV = [("live", "Live Board", "◉"),
       ("performance", "Performance", "▤"),
       ("encounters", "Encounters", "⌖"),
       ("sessions", "Sessions", "◷"),
       ("inventory", "Collection", "❖"),
       ("crosshair", "Crosshair", "✛"),
       ("display", "Display", "❂")]

NAV_SECTIONS = [
    ("MAIN", ["live", "performance", "encounters", "sessions"]),
    ("TOOLS", ["inventory", "crosshair", "display"]),
]
NAV_ICONS = {k: i for k, _l, i in NAV}
NAV_LABELS = {k: l for k, l, _i in NAV}
SIDEBAR_W = 208


class SightwareApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sightware")
        self.configure(background=BG)
        self.minsize(1080, 660)
        # always start maximized for the full dashboard experience
        self.state("zoomed")

        # core first: window restore and the art cache both read settings
        self.core = AppCore()
        self._fonts = apply(self)
        self._apply_window_icon()
        self._dark_title_bar()

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

        self._build_body()
        self._build_statusbar()

        self.core.start_services()
        self.after(500, self._start_crosshair_engine)
        self.after(2500, self._startup_update_check)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda e: self.force_refresh())
        self.bind("<Control-k>", lambda e: (self._command_palette(), "break")[1])
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
            self.iconbitmap(self._resource("sightware.ico"))
        except Exception:
            try:
                self.iconphoto(True, tk.PhotoImage(
                    file=self._resource("assets", "sightware-brand-256.png")))
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

    # ── live theme switching ───────────────────────────────────
    def apply_theme_variant(self, name: str) -> None:
        import sys as _sys
        import gui.theme as theme
        theme.set_variant(name)
        accents = ("RED", "RED_DARK", "RED_SOFT", "ORANGE", "GRAD_RULE")
        for mod_name, mod in list(_sys.modules.items()):
            if mod_name.startswith("gui") and hasattr(mod, "RED"):
                for n in accents:
                    if hasattr(theme, n):
                        setattr(mod, n, getattr(theme, n))
        theme.apply(self)
        # rebuild chrome + tabs so every canvas/label picks up the new accent
        active = self._active or "live"
        for frame in list(self._tabs.values()):
            try:
                frame.destroy()
            except Exception:
                pass
        self._tabs.clear()
        self._tab_cache.clear()
        for w in self.shell.winfo_children():
            w.destroy()
        self._build_body()
        self.show_tab(active)

    # ── command palette (Ctrl+K) ───────────────────────────────
    def _command_palette(self) -> None:
        actions = [("Live Board", lambda: self.show_tab("live")),
                   ("Performance", lambda: self.show_tab("performance")),
                   ("Encounters", lambda: self.show_tab("encounters")),
                   ("Sessions", lambda: self.show_tab("sessions")),
                   ("Collection", lambda: self.show_tab("inventory")),
                   ("Crosshair", lambda: self.show_tab("crosshair")),
                   ("Display", lambda: self.show_tab("display")),
                   ("Settings", self.open_settings),
                   ("Refresh now", self.force_refresh),
                   ("Toggle sidebar", self._toggle_sidebar)]
        try:
            for slot in self.core.all_settings().get("crosshairQuickloadHotkeys", []):
                pass
        except Exception:
            pass
        for preset in [p["name"] for p in _library_names()]:
            actions.append((f"Load crosshair: {preset}",
                            lambda n=preset: self._palette_load_crosshair(n)))
        dlg = tk.Toplevel(self)
        dlg.title("Command palette")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry(f"+{self.winfo_rootx() + 260}+{self.winfo_rooty() + 120}")
        var = tk.StringVar()
        ent = tk.Entry(dlg, textvariable=var, bg=BG_RAISED, fg=TEXT,
                       insertbackground=RED, bd=0, font=("Segoe UI", 11))
        ent.pack(fill="x", padx=14, pady=(14, 8), ipady=7)
        lb = tk.Listbox(dlg, bg=BG_RAISED, fg=TEXT, bd=0, height=10,
                        highlightthickness=1, highlightbackground=LINE,
                        selectbackground=RED, activestyle="none",
                        font=("Segoe UI", 10))
        lb.pack(fill="x", padx=14, pady=(0, 14))

        def render(_e=None):
            q = var.get().casefold()
            lb.delete(0, "end")
            for label, _cmd in actions:
                if q in label.casefold():
                    lb.insert("end", label)
            if lb.size():
                lb.selection_set(0)
        var.trace_add("write", render)

        def run(_e=None):
            sel = lb.curselection()
            if not sel and lb.size():
                lb.selection_set(0)
            sel = lb.curselection()
            if sel:
                label = lb.get(sel[0])
                for a_label, a_cmd in actions:
                    if a_label == label:
                        dlg.destroy()
                        a_cmd()
                        return
        ent.bind("<Return>", run)
        lb.bind("<Double-Button-1>", run)
        ent.bind("<Down>", lambda e: (lb.selection_clear(0, "end"),
                                      lb.selection_set(min(lb.curselection()[0] + 1,
                                                           lb.size() - 1)
                                                       if lb.curselection() else 0),
                                      "break")[2])
        ent.bind("<Up>", lambda e: (lb.selection_clear(0, "end"),
                                    lb.selection_set(max(lb.curselection()[0] - 1, 0)
                                                     if lb.curselection() else 0),
                                    "break")[2])
        ent.bind("<Escape>", lambda e: dlg.destroy())
        render()
        ent.focus_set()

    def _palette_load_crosshair(self, name):
        import crosshair_store as store
        cfg = store.load_from_library(name)
        if cfg:
            self.crosshair_engine.save_crosshair(cfg)
            self.show_tab("crosshair")
            self.toast.show(f'Loaded "{name}".', kind="ok")

    # ── window shell: sidebar + main column ────────────────────
    def _build_body(self) -> None:
        self.shell = tk.Frame(self, bg=BG)
        shell = self.shell
        shell.pack(fill="both", expand=True)

        # ── sidebar ─────────────────────────────────────────────
        self.sidebar = tk.Frame(shell, bg=BG_RAISED, width=SIDEBAR_W)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        collapse_row = tk.Frame(self.sidebar, bg=BG_RAISED)
        collapse_row.pack(fill="x", pady=(10, 0), padx=8)
        self._sidebar_collapsed = False
        self.collapse_btn = tk.Label(collapse_row, text="«", bg=BG_RAISED,
                                     fg=TEXT_DIM, font=("Segoe UI", 11, "bold"),
                                     cursor="hand2", padx=6)
        self.collapse_btn.pack(side="right")
        self.collapse_btn.bind("<Button-1>",
                               lambda e: self._toggle_sidebar())
        try:
            if self.core.all_settings().get("sidebarCollapsed"):
                self.after(200, self._toggle_sidebar)
        except Exception:
            pass

        brand = tk.Frame(self.sidebar, bg=BG_RAISED)
        brand.pack(fill="x", padx=18, pady=(8, 14))
        # the real Sightware logo (assets/sightware-brand-256.png)
        try:
            from PIL import Image as _PILImage
            from PIL import ImageTk as _PILImageTk
            _img = _PILImage.open(self._resource("assets", "sightware-brand-256.png"))
            self._brand_photo = _PILImageTk.PhotoImage(
                _img.resize((34, 34), _PILImage.LANCZOS))
            tk.Label(brand, image=self._brand_photo, bg=BG_RAISED
                     ).pack(side="left")
        except Exception:
            # fallback if the asset/Pillow is unavailable
            badge = tk.Canvas(brand, width=34, height=34, bg=BG_RAISED,
                              highlightthickness=0)
            badge.pack(side="left")
            badge.create_text(17, 17, text="V", fill=RED,
                              font=("Segoe UI", 15, "bold"))
        brand_txt = tk.Frame(brand, bg=BG_RAISED)
        brand_txt.pack(side="left", padx=(10, 0))
        tk.Label(brand_txt, text="SIGHTWARE", bg=BG_RAISED, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(brand_txt, text="LOCAL EDITION", bg=BG_RAISED, fg=TEXT_FAINT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")

        self._nav_items = {}
        self._active = None

        for title, keys in NAV_SECTIONS:
            tk.Label(self.sidebar, text=title, bg=BG_RAISED, fg=TEXT_FAINT,
                     font=("Segoe UI", 7, "bold"), anchor="w"
                     ).pack(fill="x", padx=22, pady=(14, 4))
            for key in keys:
                self._make_nav_item(key)

        foot = tk.Frame(self.sidebar, bg=BG_RAISED)
        foot.pack(side="bottom", fill="x", padx=16, pady=12)
        tk.Label(foot, text="100% local — no telemetry.\nData stays on this PC.",
                 bg=BG_RAISED, fg=TEXT_FAINT, font=("Segoe UI", 8),
                 justify="left", anchor="w").pack(fill="x")

        # ── main column: header + content ───────────────────────
        self._main = tk.Frame(shell, bg=BG)
        self._main.pack(side="left", fill="both", expand=True)
        self._build_header()

        self.content = tk.Frame(self._main, bg=BG)
        self.content.pack(fill="both", expand=True)
        self._tabs = {}
        # centered content column like the web dashboard
        self.column = tk.Frame(self.content, bg=BG)
        self.column.place(relx=0.5, rely=0, anchor="n", width=1600,
                          relheight=1)

        def _fit_column(e, col=self.column):
            # fill the available space between sidebar edges with padding
            col.place_configure(width=max(720, min(1800, e.width - 36)))
        self.content.bind("<Configure>", _fit_column, add="+")

    def _toggle_sidebar(self) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        collapsed = self._sidebar_collapsed
        self.sidebar.configure(width=64 if collapsed else SIDEBAR_W)
        for w in self.sidebar.winfo_children():
            if w is self.collapse_btn.master:
                continue
            if w is getattr(self, "_brand_frame", None):
                continue
        # hide/show everything except the collapse button row
        collapse_btn_row = self.collapse_btn.master
        for w in self.sidebar.winfo_children():
            if w is collapse_btn_row:
                continue
            try:
                w.pack_forget()
        # noqa - re-pack below
            except Exception:
                pass
        if not collapsed:
            # re-pack in original order: brand, section labels, items, footer
            self._rebuild_sidebar()
        else:
            collapse_btn_row.pack_forget()
            collapse_btn_row.pack(fill="x", pady=(10, 0), padx=8)
            self.collapse_btn.configure(text="»")
            # icon-only items
            for key in NAV_LABELS:
                item = tk.Label(self.sidebar, text=NAV_ICONS[key],
                                bg=BG_RAISED, fg=TEXT_DIM,
                                font=("Segoe UI", 12), width=3,
                                cursor="hand2", pady=6)
                item.pack()
                item.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
                self._tooltip(item, NAV_LABELS[key])
        try:
            self.core.update_settings({"sidebarCollapsed": collapsed})
        except Exception:
            pass

    def _rebuild_sidebar(self):
        for w in self.sidebar.winfo_children():
            w.destroy()
        self._nav_items = {}
        self.collapse_btn = None
        collapse_row = tk.Frame(self.sidebar, bg=BG_RAISED)
        collapse_row.pack(fill="x", pady=(10, 0), padx=8)
        self.collapse_btn = tk.Label(collapse_row, text="«", bg=BG_RAISED,
                                     fg=TEXT_DIM, font=("Segoe UI", 11, "bold"),
                                     cursor="hand2", padx=6)
        self.collapse_btn.pack(side="right")
        self.collapse_btn.bind("<Button-1>",
                               lambda e: self._toggle_sidebar())
        brand = tk.Frame(self.sidebar, bg=BG_RAISED)
        brand.pack(fill="x", padx=18, pady=(8, 14))
        try:
            from PIL import Image as _I
            from PIL import ImageTk as _IT
            img = _I.open(self._resource("assets", "sightware-brand-256.png"))
            self._brand_photo = _IT.PhotoImage(img.resize((34, 34), _I.LANCZOS))
            tk.Label(brand, image=self._brand_photo, bg=BG_RAISED
                     ).pack(side="left")
        except Exception:
            pass
        brand_txt = tk.Frame(brand, bg=BG_RAISED)
        brand_txt.pack(side="left", padx=(10, 0))
        tk.Label(brand_txt, text="SIGHTWARE", bg=BG_RAISED, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(brand_txt, text="LOCAL EDITION", bg=BG_RAISED, fg=TEXT_FAINT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")
        for title, keys in NAV_SECTIONS:
            tk.Label(self.sidebar, text=title, bg=BG_RAISED, fg=TEXT_FAINT,
                     font=("Segoe UI", 7, "bold"), anchor="w"
                     ).pack(fill="x", padx=22, pady=(14, 4))
            for key in keys:
                self._make_nav_item(key)
        foot = tk.Frame(self.sidebar, bg=BG_RAISED)
        foot.pack(side="bottom", fill="x", padx=16, pady=12)
        tk.Label(foot, text="100% local — no telemetry.",
                 bg=BG_RAISED, fg=TEXT_FAINT,
                 font=("Segoe UI", 8)).pack(fill="x")
        self._refresh_nav_states()

    def _tooltip(self, widget, text):
        tip = {"win": None}
        def enter(_e):
            if tip["win"]:
                return
            x = widget.winfo_rootx() + widget.winfo_width() + 6
            y = widget.winfo_rooty() + 8
            tip["win"] = tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg=CARD_HI, fg=TEXT, padx=8, pady=3,
                     font=("Segoe UI", 8)).pack()
        def leave(_e):
            if tip["win"]:
                tip["win"].destroy()
                tip["win"] = None
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")

    def _make_nav_item(self, key: str) -> None:
        label = NAV_LABELS[key]
        icon = NAV_ICONS[key]
        row = tk.Frame(self.sidebar, bg=BG_RAISED, cursor="hand2")
        row.pack(fill="x", padx=10, pady=1)
        indicator = tk.Frame(row, bg=BG_RAISED, width=3)
        indicator.pack(side="left", fill="y", padx=(0, 8), pady=5)
        body = tk.Frame(row, bg=BG_RAISED)
        body.pack(fill="x")
        tk.Label(body, text=icon, bg=BG_RAISED, fg=TEXT_DIM,
                 font=("Segoe UI", 11), width=2, anchor="center"
                 ).pack(side="left", pady=7)
        tk.Label(body, text=label, bg=BG_RAISED, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold"), anchor="w"
                 ).pack(side="left", padx=(6, 0), pady=7)
        row._indicator = indicator
        row._labels = [w for w in (body, *body.winfo_children())]

        def hover_on(_e, r=row):
            if self._active != key:
                self._nav_style(r, CARD_HI, TEXT)

        def hover_off(_e, r=row):
            if self._active != key:
                self._nav_style(r, BG_RAISED, TEXT_DIM)

        for w in (row, *row._labels):
            w.bind("<Enter>", hover_on)
            w.bind("<Leave>", hover_off)
            w.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
        self._nav_items[key] = row

    def _nav_style(self, row, bg, fg, indicator=None):
        row.configure(bg=bg)
        row._indicator.configure(bg=indicator or bg)
        for w in row._labels:
            try:
                w.configure(bg=bg)
                if isinstance(w, tk.Label) and w.cget("text") not in NAV_ICONS.values():
                    w.configure(fg=fg)
            except tk.TclError:
                pass

    def _refresh_nav_states(self):
        for k, row in self._nav_items.items():
            if k == self._active:
                self._nav_style(row, CARD, TEXT, indicator=RED)
                for w in row._labels:
                    if isinstance(w, tk.Label) and w.cget("text") in NAV_ICONS.values():
                        w.configure(fg=RED)
            else:
                self._nav_style(row, BG_RAISED, TEXT_DIM)
                for w in row._labels:
                    if isinstance(w, tk.Label) and w.cget("text") in NAV_ICONS.values():
                        w.configure(fg=TEXT_DIM)

    # ── header (top bar of the main column) ────────────────────
    def _build_header(self) -> None:
        header = tk.Frame(self._main, bg=BG, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.page_title = tk.Label(header, text="Live Board", bg=BG, fg=TEXT,
                                   font=("Segoe UI", 15, "bold"))
        self.page_title.pack(side="left", padx=(22, 8))

        self.source_pill = Pill(header, "—", bg=CARD, fg=TEXT_DIM,
                                font=("Segoe UI", 8, "bold"))
        self.source_pill.pack(side="left", padx=(6, 4))
        self.state_pill = Pill(header, "—", bg=CARD_HI, fg=TEXT,
                               font=("Segoe UI", 8, "bold"))
        self.state_pill.pack(side="left", padx=2)
        self.update_btn = ttk.Button(header, text="", style="Success.TButton",
                                     command=self._install_update)
        # packed only when an update is actually available

        btns = tk.Frame(header, bg=BG)
        btns.pack(side="right", padx=(0, 16))
        ttk.Button(btns, text="⟳ Refresh", style="Ghost.TButton",
                   command=self.force_refresh).pack(side="left", padx=3)
        ttk.Button(btns, text="⚙  Settings", style="Ghost.TButton",
                   command=self.open_settings).pack(side="left", padx=3)
        AccentRule(self._main, colors=[LINE_SOFT, RED, LINE_SOFT],
                   height=2).pack(fill="x")

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
        self._refresh_nav_states()
        if getattr(self, "page_title", None) and self.page_title.winfo_exists():
            self.page_title.configure(text=NAV_LABELS.get(key, key))
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
        tk.Label(footer, text="Sightware is 100% local — dashboard, settings, "
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
        det = tk.Label(footer, text="Privacy & policy details", bg=BG_RAISED, fg=RED_SOFT,
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
            target=self._poll_loop, name="sightware-poll", daemon=True)
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
                if state == "INGAME" and                         self.core.all_settings().get("lowImpactInGame", True):
                    delay = POLL_INGAME + 2.0
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
        try:
            if state == "INGAME" and                     self.core.all_settings().get("lowImpactInGame", True):
                cadence = POLL_INGAME + 2.0
        except Exception:
            pass
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

    # ── updates ────────────────────────────────────────────────
    def _startup_update_check(self) -> None:
        try:
            if not self.core.all_settings().get("autoUpdates"):
                return
        except Exception:
            return
        self.run_bg(
            lambda: __import__("gui.update_check", fromlist=["check_for_update"]
                               ).check_for_update(),
            self._on_update_check)

    def _on_update_check(self, result) -> None:
        if result.get("status") != "update_available":
            return
        self._latest_version = result.get("latest", "")
        try:
            self.update_btn.configure(
                text=f"⬆ Update v{self._latest_version}")
            self.update_btn.pack(side="left", padx=(10, 4))
        except tk.TclError:
            pass
        self.notify(f"Sightware v{self._latest_version} is available — "
                    "use the Update button to install.", kind="info")

    def _install_update(self) -> None:
        from tkinter import messagebox
        version = getattr(self, "_latest_version", "?")
        if not messagebox.askyesno(
                "Sightware update",
                f"Install update v{version} now?\n\n"
                "Your data (history, crosshair library, settings) is kept. "
                "Sightware restarts when finished."):
            return
        self.update_btn.configure(state="disabled", text="Updating…")
        import gui.update_check as upd
        self.run_bg(
            lambda: upd.perform_update(getattr(self, "_latest_version", None),
                                       log=lambda m: self._post_ui(
                                           lambda: self.toast.show(m))),
            self._on_update_installed,
            on_error=lambda e: self._post_ui(
                lambda: self.toast.show(f"Update failed: {e}", kind="error")))

    def _on_update_installed(self, result) -> None:
        if not result.get("ok"):
            self.toast.show(result.get("message", "Update failed"), kind="error")
            self.update_btn.configure(state="normal")
            return
        self.toast.show(result.get("message", "Updated."), kind="ok")
        self.after(1200, self._restart_after_update)

    def _restart_after_update(self) -> None:
        import gui.update_check as upd
        try:
            self._shutting = True
            self._poll_stop.set()
            self._queue_monitor.stop()
            try:
                self.crosshair_engine.stop()
            except Exception:
                pass
            try:
                self.core.stop_services()
            except Exception:
                pass
            self.destroy()
        except Exception:
            pass
        try:
            upd.restart_app()
        except Exception as e:
            self.toast.show(f"Installed, but auto-restart failed: {e} — "
                            "start Sightware manually.", kind="error")

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
    def _session_recap(self, recap: dict) -> None:
        """Quit-time recap when a tracked session is running."""
        dlg = tk.Toplevel(self)
        dlg.title("Session recap")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text="SESSION IN PROGRESS", bg=BG, fg=AMBER,
                 font=("Segoe UI", 9, "bold")).pack(pady=(16, 4))
        stats = tk.Frame(dlg, bg=BG)
        stats.pack(padx=20)
        for i, (k, v) in enumerate((recap.get("stats") or recap).items()
                                   if isinstance(recap, dict) else []):
            if not isinstance(v, (int, float, str)):
                continue
            tk.Label(stats, text=f"{k}: {v}", bg=BG, fg=TEXT,
                     font=("Segoe UI", 10)).grid(row=i // 2, column=i % 2,
                                                 sticky="w", padx=10, pady=3)
        tk.Label(dlg, text="End this session before quitting, or keep it "
                 "running in the background?", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(pady=(10, 12))

        def end_and_quit():
            try:
                import session_tracker
                session_tracker.end_active()
            except Exception:
                pass
            dlg.destroy()
            self._on_close()
        row = tk.Frame(dlg, bg=BG)
        row.pack(pady=(0, 16))
        ttk.Button(row, text="End session & quit", style="Accent.TButton",
                   command=end_and_quit).pack(side="left", padx=4)
        ttk.Button(row, text="Keep running", style="Ghost.TButton",
                   command=dlg.destroy).pack(side="left", padx=4)

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
        # active session? show a recap before shutting down. Gated on an
        # actually-active session — a stale match recap alone shouldn't
        # block quitting.
        try:
            import session_tracker
            recap = (session_tracker.current_recap()
                     if session_tracker.any_active_session() else None)
        except Exception:
            recap = None
        if recap:
            self._session_recap(recap)
            return
        self._shutting = True
        self._poll_stop.set()
        self._queue_monitor.stop()
        try:
            self.crosshair_engine.stop()
        except Exception:
            pass
        try:
            self.core.update_settings({"lastTab": self._active or ""})
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
    app = SightwareApp()
    app.mainloop()
