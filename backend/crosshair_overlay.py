"""Crosshair Overlay — click-through overlay engine.

Vanguard-friendly by construction:

* The overlay is a plain topmost layered window that only draws its own
  pixels. It never opens a handle to any process (least of all the game),
  never reads or writes memory, never injects, never hooks, never captures.
* ``WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`` keeps clicks flowing straight to
  the game; ``WS_EX_TOOLWINDOW`` keeps it out of the taskbar/alt-tab.
* Hotkey input comes from passive ``GetAsyncKeyState`` polling
  (see crosshair_input) — no input hooks are installed.
* App focus whitelisting matches foreground **window titles** (cached
  window properties only — no ``OpenProcess``).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json

import tkinter as tk

import crosshair_store as store
import crosshair_render as render
from crosshair_input import GlobalInput, foreground_matches

_user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
LWA_COLORKEY = 0x00000001
CHROMA = 0x030201            # BGR for RGB(1, 2, 3) — the overlay's transparent color
CHROMA_HEX = "#010203"

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _user32.GetWindowLongPtrW = _user32.GetWindowLongPtrW
    _user32.SetWindowLongPtrW = _user32.SetWindowLongPtrW
else:  # pragma: no cover — 32-bit fallback
    _user32.GetWindowLongPtrW = _user32.GetWindowLongW
    _user32.SetWindowLongPtrW = _user32.SetWindowLongW


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def monitor_bounds() -> list[dict]:
    """All monitor rects, primary first. Pure display enumeration."""
    out: list[dict] = []

    def _cb(hMonitor, hdc, lprc, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
            r = mi.rcMonitor
            out.append({"x": r.left, "y": r.top, "w": r.right - r.left,
                        "h": r.bottom - r.top,
                        "primary": bool(mi.dwFlags & 1)})
        return True

    MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.POINTER(wt.RECT), wt.LPARAM)
    _user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    out.sort(key=lambda m: not m["primary"])
    return out


class OverlayEngine:
    """Owns the overlay windows, hotkey handling and visibility state."""

    def __init__(self, root: tk.Misc, post) -> None:
        self.root = root
        self.post = post                     # callable(fn) → run on UI thread
        self.crosshair: dict = {}
        self.settings: dict = {}
        self.ads_crosshair: dict | None = None
        self.windows: list[tk.Toplevel] = []
        self.input = GlobalInput(post)
        self.input.on_event = self._on_input
        self.input.on_capture = self._on_capture
        self.capture_target: tuple | None = None   # (kind, index) while binding

        # state
        self.hidden_by_toggle = False
        self.ads_pressed = False
        self.in_whitelist = True
        self.running = False
        self._last_app = None
        self._per_app_active = False

        self.on_status = None                # fn(status_dict) → UI
        self.on_crosshair_changed = None     # fn(cfg) → UI (external load)
        self._wl_timer = None
        self._topmost_timer = None

    # ── lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.reload_config(start=True)

    def stop(self) -> None:
        self.running = False
        self.input.stop()
        for w in self.windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.windows.clear()
        self._cancel_timers()

    def _cancel_timers(self) -> None:
        for t in (self._wl_timer, self._topmost_timer):
            if t:
                try:
                    self.root.after_cancel(t)
                except tk.TclError:
                    pass
        self._wl_timer = self._topmost_timer = None

    def reload_config(self, start: bool = False) -> None:
        self.crosshair = store.get_crosshair()
        self.settings = store.get_overlay_settings()
        self._load_ads_crosshair()
        if start:
            self.input.start()
        self._rebuild_windows()
        self._schedule_whitelist_poll()
        self._schedule_topmost()
        self.resolve_and_render()

    def _load_ads_crosshair(self) -> None:
        s = self.settings
        if s.get("enableAds") and s.get("adsAction") == "switch" and s.get("adsPath"):
            self.ads_crosshair = store.load_from_library(s["adsPath"])
        else:
            self.ads_crosshair = None
        if not s.get("enableAds"):
            self.ads_pressed = False

    def save_settings(self, cfg: dict) -> dict:
        self.settings = store.save_overlay_settings(cfg)
        self._load_ads_crosshair()
        self._rebuild_windows()
        self._schedule_whitelist_poll()
        self.resolve_and_render()
        return self.settings

    def save_crosshair(self, cfg: dict) -> None:
        self.crosshair = json.loads(json.dumps(cfg))
        store.save_crosshair(self.crosshair)
        self.resolve_and_render()

    def set_crosshair_runtime(self, cfg: dict | None) -> None:
        """Switch crosshair without persisting (preview / external load uses store)."""
        if cfg is None:
            self.crosshair = store.get_crosshair()
        else:
            self.crosshair = json.loads(json.dumps(cfg))
        self.resolve_and_render()

    # ── overlay windows ────────────────────────────────────────

    def _target_bounds(self) -> list[dict]:
        monitors = monitor_bounds()
        if not monitors:
            monitors = [{"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True}]
        target = str(self.settings.get("targetDisplay", "primary"))
        if target == "all":
            return monitors
        if target == "primary":
            return [monitors[0]]
        try:
            idx = int(target)
            return [monitors[idx]] if 0 <= idx < len(monitors) else [monitors[0]]
        except (TypeError, ValueError):
            return [monitors[0]]

    def _rebuild_windows(self) -> None:
        if not self.settings.get("enabled", True):
            self._destroy_windows()
            return
        wanted = self._target_bounds()
        current = [(w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height())
                   for w in self.windows]
        need_new = len(wanted) != len(self.windows) or any(
            (b["x"], b["y"], b["w"], b["h"]) not in current for b in wanted)
        if not need_new:
            return
        self._destroy_windows()
        for b in wanted:
            self._make_window(b)

    def _destroy_windows(self) -> None:
        for w in self.windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.windows.clear()

    def _make_window(self, b: dict) -> None:
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.geometry(f"{b['w']}x{b['h']}+{b['x']}+{b['y']}")
        w.configure(background=CHROMA_HEX)
        w.attributes("-topmost", True)
        try:
            w.attributes("-transparentcolor", CHROMA_HEX)
        except tk.TclError:
            pass
        cv = tk.Canvas(w, bg=CHROMA_HEX, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        cv.image_refs: list = []
        w.canvas = cv
        w.protocol("WM_DELETE_WINDOW", lambda: None)
        w.bind("<FocusIn>", lambda e: "break")   # never take focus
        self.windows.append(w)
        w.update_idletasks()
        self._apply_ex_style(w)
        self._assert_topmost(w)

    def _apply_ex_style(self, w: tk.Toplevel) -> None:
        try:
            # winfo_id() is Tk's *child* window — click-through only works when
            # the styles sit on the real top-level HWND (its ancestor).
            child = w.winfo_id()
            hwnd = _user32.GetAncestor(child, 2) or child   # GA_ROOT = 2
            style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
            # Tk's -transparentcolor already set the colorkey on the wrapper;
            # re-assert it on the same HWND we just styled.
            _user32.SetLayeredWindowAttributes(hwnd, CHROMA, 0, LWA_COLORKEY)
            self._assert_topmost(w)
        except Exception:
            pass

    def _assert_topmost(self, w: tk.Toplevel) -> None:
        try:
            hwnd = _user32.GetAncestor(w.winfo_id(), 2) or w.winfo_id()
            _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass

    def _schedule_topmost(self) -> None:
        if self._topmost_timer:
            return
        def tick():
            self._topmost_timer = None
            if not self.running:
                return
            for w in self.windows:
                self._assert_topmost(w)
            self._topmost_timer = self.root.after(10_000, tick)
        self._topmost_timer = self.root.after(10_000, tick)

    # ── visibility state machine ───────────────────────────────

    def _active_crosshair(self) -> dict | None:
        s = self.settings
        if self.ads_pressed and s.get("enableAds") and \
                s.get("adsAction") == "switch" and self.ads_crosshair:
            return self.ads_crosshair
        return self.crosshair

    def _visible(self) -> bool:
        s = self.settings
        if not s.get("enabled", True):
            return False
        if self.hidden_by_toggle:
            return False
        if self.ads_pressed and s.get("enableAds") and s.get("adsAction") == "hide":
            return False
        if s.get("whitelistEnabled") and not self.in_whitelist:
            return False
        return self._active_crosshair() is not None

    def resolve_and_render(self) -> None:
        visible = self._visible()
        cfg = self._active_crosshair() if visible else None
        for w in self.windows:
            cv = w.canvas
            cv.delete("all")
            cv.image_refs.clear()
            if visible and cfg:
                sx = float(self.settings.get("offsetX", 0) or 0)
                sy = float(self.settings.get("offsetY", 0) or 0)
                scaled = self._scaled(cfg, float(self.settings.get("scale", 1) or 1))
                render.draw_crosshair(cv, w.winfo_width() / 2 + sx,
                                      w.winfo_height() / 2 + sy, scaled,
                                      image_holder=cv.image_refs)
        if self.on_status:
            status = {"visible": visible, "hiddenByToggle": self.hidden_by_toggle,
                      "ads": self.ads_pressed, "whitelisted": self.in_whitelist,
                      "windows": len(self.windows)}
            self.on_status(status)

    @staticmethod
    def _scaled(cfg: dict, scale: float) -> dict:
        if scale == 1.0:
            return cfg
        out = json.loads(json.dumps(cfg))
        c = out["crosshair"]
        style = c.get("style")
        if style in ("cross", "circle"):
            for key in ("gap", "length", "thickness"):
                v = round(float(c.get(key, 0) or 0) * scale, 3)
                c[key] = max(v, 0.1) if key in ("thickness", "length") else max(v, 0)
            c.setdefault("outline", {})
            c["outline"]["thickness"] = round(float(c["outline"].get("thickness", 0) or 0) * scale, 2)
            d = c.get("dot", {}) or {}
            d["size"] = round(float(d.get("size", 0) or 0) * scale, 2)
            d.setdefault("outline", {})
            d["outline"]["thickness"] = round(float(d["outline"].get("thickness", 0) or 0) * scale, 2)
            c["dot"] = d
        elif style == "pixels":
            out["pixels"]["scale"] = float(out["pixels"].get("scale", 1) or 1) * scale
        elif style == "custom":
            out["custom"]["scale"] = float(out["custom"].get("scale", 1) or 1) * scale
        return out

    # ── whitelist (window-title matching, no process handles) ──

    def _schedule_whitelist_poll(self) -> None:
        if self._wl_timer:
            try:
                self.root.after_cancel(self._wl_timer)
            except tk.TclError:
                pass
            self._wl_timer = None
        if not self.settings.get("whitelistEnabled"):
            if not self.in_whitelist:
                self.in_whitelist = True
                self.resolve_and_render()
            return
        self._whitelist_tick()

    def _whitelist_tick(self) -> None:
        if not self.running or not self.settings.get("whitelistEnabled"):
            return
        entries = [e for e in self.settings.get("whitelist", []) if e.get("name")]
        names = {e["name"] for e in entries}
        # which whitelisted app (if any) is focused right now?
        active_app = None
        if names:
            try:
                from crosshair_input import foreground_name
                title = foreground_name()
            except Exception:
                title = ""
            if title:
                for n in names:
                    if n.casefold() in title.casefold():
                        active_app = n
                        break
        found = active_app is not None

        # per-app crosshair memory: swap presets when the focused app changes
        if active_app != self._last_app:
            self._last_app = active_app
            per_app = store.get_per_app()
            wanted = per_app.get(active_app or "", "") if active_app else ""
            cfg = store.load_from_library(wanted) if wanted else None
            if cfg is not None:
                self.crosshair = cfg
                self._per_app_active = True
            elif self._per_app_active:
                # leaving a per-app preset: back to the user's base crosshair
                self.crosshair = store.get_crosshair()
                self._per_app_active = False
            self.resolve_and_render()
            if self.on_crosshair_changed and cfg is not None:
                self.on_crosshair_changed(cfg)

        if found != self.in_whitelist:
            self.in_whitelist = found
            self.resolve_and_render()
        self._wl_timer = self.root.after(400, self._whitelist_tick)

    # ── input events ───────────────────────────────────────────

    @staticmethod
    def _match(key: str, binding: str) -> bool:
        if not binding or not binding.strip():
            return False
        kb = {p.strip().casefold() for p in key.split("+")}
        want = [p.strip().casefold() for p in binding.split("+")]
        return all(p in kb for p in want)

    def _on_input(self, key: str, state: str) -> None:
        s = self.settings
        if not s.get("enabled", True):
            return
        if state == "DOWN":
            # quickload slots
            for i, slot in enumerate(s.get("quickload", [])):
                if self._match(key, slot.get("key", "")) and slot.get("crosshair"):
                    cfg = store.load_from_library(slot["crosshair"])
                    if cfg:
                        self.crosshair = cfg
                        store.save_crosshair(cfg)
                        self.resolve_and_render()
                        if self.on_crosshair_changed:
                            self.on_crosshair_changed(cfg)
                    return
        if s.get("enableAds") and (self._match(key, s.get("adsKey", "")) or
                                   self._match(key, s.get("adsKey2", ""))):
            if state == "DOWN":
                if s.get("adsBehaviour") == "toggle":
                    self.ads_pressed = not self.ads_pressed
                else:
                    self.ads_pressed = True
                self.resolve_and_render()
            elif state == "UP" and s.get("adsBehaviour") != "toggle":
                self.ads_pressed = False
                self.resolve_and_render()
            return
        if self._match(key, s.get("toggleKey", "")) or self._match(key, s.get("toggleKey2", "")):
            if state == "DOWN":
                self.hidden_by_toggle = not self.hidden_by_toggle
                self.resolve_and_render()

    # ── keybind capture ────────────────────────────────────────

    def begin_capture(self, kind: str, index: int = -1) -> None:
        self.capture_target = (kind, index)
        self.input.begin_capture()

    def cancel_capture(self) -> None:
        self.capture_target = None
        self.input.cancel_capture()

    def _on_capture(self, key: str) -> None:
        target = self.capture_target
        self.capture_target = None
        if target:
            kind, idx = target
            if self.on_capture_done:
                self.on_capture_done(kind, idx, key)

    on_capture_done = None    # fn(kind, index, key) → UI stores the binding
