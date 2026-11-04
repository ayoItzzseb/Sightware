"""Crosshair overlay smoke test: store round-trip, renderer, tab UI and the
overlay engine — all without stealing focus (windows are created then hidden).

Run:  python -I tests/smoke_crosshair.py
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["VALTIX_QUIET"] = "1"

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("Sightware — crosshair overlay smoke test\n")

    # the user's live overlay.json may legitimately have the overlay switched
    # off — snapshot and force it on for the engine checks, restore afterwards
    import json
    overlay_file = ROOT / "backend" / "data" / "crosshair" / "overlay.json"
    saved_overlay = overlay_file.read_text(encoding="utf-8") if overlay_file.is_file() else None
    if saved_overlay is not None:
        data = json.loads(saved_overlay)
        data["enabled"] = True
        overlay_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── store ──────────────────────────────────────────────────
    print("store")
    import crosshair_store as store
    cfg = store.get_crosshair()
    check("crosshair config loads", isinstance(cfg.get("crosshair"), dict)
          and cfg["crosshair"].get("style") in ("cross", "circle", "pixels", "custom"),
          str(cfg.get("crosshair", {}).get("style")))
    st = store.get_overlay_settings()
    check("overlay settings load", "targetDisplay" in st and "enabled" in st)
    name = store.save_to_library("smoke-test", cfg)
    check("save to library", name == "smoke-test")
    check("library lists it", any(p["name"] == "smoke-test" for p in store.library_list()))
    loaded = store.load_from_library("smoke-test")
    check("load from library round-trip",
          loaded is not None and loaded["crosshair"]["style"] == cfg["crosshair"]["style"])
    check("delete from library", store.delete_from_library("smoke-test"))

    # ── renderer ───────────────────────────────────────────────
    print("renderer")
    import crosshair_render as render
    check("cross extent", render.config_extent(cfg)[0] > 0)

    # ── engine + tab UI ────────────────────────────────────────
    print("engine + tab")
    import tkinter as tk
    from gui.app import SightwareApp
    app = SightwareApp()
    app.withdraw()

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    pump(1.2)

    px = base64.b64encode(_png()).decode()
    cfg_px = {**cfg, "crosshair": {**cfg["crosshair"], "style": "pixels"},
              "pixels": {"data": px, "scale": 2, "tint": "#FF0000FF"}}
    check("pixels photo renders", render.make_image_photo(cfg_px) is not None)

    eng = app.crosshair_engine
    check("engine started", eng.running)
    check("overlay windows created", len(eng.windows) >= 1,
          f"got {len(eng.windows)}")

    tab = app._make_tab("crosshair")
    app.show_tab("crosshair")
    pump(0.8)
    check("crosshair tab builds", tab.winfo_exists())
    check("preview canvas exists", hasattr(tab, "preview"))
    check("library cards rendered", len(tab._lib_cards) > 0,
          f"got {len(tab._lib_cards)}")

    # style switch round-trip
    tab._set_style("circle")
    check("style switch", tab._working()["crosshair"]["style"] == "circle")
    before = bool(tab._working()["crosshair"]["lines"][0])
    tab._toggle_line(0)
    check("line toggle flips", tab._working()["crosshair"]["lines"][0] is not before)
    tab._toggle_line(0)
    check("line toggle flips back", tab._working()["crosshair"]["lines"][0] is before)
    tab._set_style("cross")
    pump(0.3)

    # visibility state machine
    eng.hidden_by_toggle = True
    eng.resolve_and_render()
    check("hide hotkey hides", not eng._visible())
    eng.hidden_by_toggle = False
    eng.resolve_and_render()
    check("unhide restores", eng._visible())
    eng.settings["whitelistEnabled"] = True
    eng.settings["whitelist"] = [{"name": "Definitely Not Running App XYZ"}]
    eng.in_whitelist = False
    check("whitelist hides", not eng._visible())
    eng.settings["whitelistEnabled"] = False
    eng.in_whitelist = True
    eng.resolve_and_render()
    check("whitelist off restores", eng._visible())

    # input matching (pure string logic)
    check("combo match", eng._match("LEFT SHIFT + F2", "LEFT SHIFT + F2"))
    check("combo no-match", not eng._match("F2", "LEFT SHIFT + F2"))
    check("mouse match", eng._match("MOUSE RIGHT", "MOUSE RIGHT"))

    # click-through: the OS itself must never hit-test to our window,
    # neither on the crosshair pixels nor anywhere else in the overlay
    import ctypes
    from ctypes import wintypes as wt
    child = eng.windows[0].winfo_id()
    user32 = ctypes.WinDLL("user32")
    hwnd = user32.GetAncestor(child, 2)  # GA_ROOT — the real top window
    style = user32.GetWindowLongPtrW(hwnd, -20)
    check("WS_EX_TRANSPARENT set", bool(style & 0x20))
    check("WS_EX_LAYERED set", bool(style & 0x80000))
    check("WS_EX_NOACTIVATE set", bool(style & 0x08000000))

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT — the real top window
    sw = eng.windows[0].winfo_screenwidth() // 2
    sh = eng.windows[0].winfo_screenheight() // 2
    our_pid = os.getpid()
    for name, px, py in (("crosshair center", sw, sh),
                         ("off-pixel area", sw + 140, sh + 140)):
        pt = POINT(px, py)
        hit = user32.WindowFromPoint(pt)
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hit, buf, 64)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hit, ctypes.byref(pid))
        check(f"click-through ({name})", pid.value != our_pid,
              f"hit our window! class={buf.value}")

    eng.stop()
    check("engine stops clean", len(eng.windows) == 0)
    app.destroy()

    if saved_overlay is not None:
        overlay_file.write_text(saved_overlay, encoding="utf-8")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} — {', '.join(FAILURES)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


def _png() -> bytes:
    """4x4 red PNG via Pillow (same encoder the pixel editor uses)."""
    from PIL import Image
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
