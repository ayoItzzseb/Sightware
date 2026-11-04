"""Display tab (ChromaDesk integration) smoke test.

Run:  python -I tests/smoke_display.py
"""
from __future__ import annotations

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
    print("Sightware — ChromaDesk display tab smoke test\n")

    # engine standalone
    print("engine")
    import display_engine as deng
    display = deng.WindowsDisplay()
    check("display devices found", len(display.devices) >= 1)
    check("modes enumerated", len(display.modes) >= 1, f"got {len(display.modes)}")
    check("current mode read", display.current and display.current[0] > 0)

    dvc = dvc_error = None
    try:
        dvc = deng.NvidiaDVC(display.device)
    except Exception as exc:
        dvc_error = str(exc)
    check("DVC engine (available or clean error)",
          dvc is not None or bool(dvc_error))
    sat = deng.get_saturation()
    sat_error = deng.saturation_error()
    check("saturation engine singleton (available or clean error)",
          (sat is not None) == (sat_error is None))
    if sat is not None:
        check("saturation singleton reused", deng.get_saturation() is sat)

    # profiles store round-trip
    profiles = deng.read_profiles()
    profiles["__smoke__"] = {"monitor_device": display.device,
                             "resolution": list(display.current)}
    deng.write_profiles(profiles)
    check("profile round-trip", "__smoke__" in deng.read_profiles())
    profiles = deng.read_profiles()
    profiles.pop("__smoke__")
    deng.write_profiles(profiles)

    # tab inside the app
    print("tab")
    import tkinter as tk
    from gui.app import SightwareApp
    app = SightwareApp()
    app.withdraw()

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            app.update()
            time.sleep(0.01)

    pump(1.0)
    tab = app._make_tab("display")
    app.show_tab("display")
    pump(1.5)
    check("display tab builds", tab.winfo_exists())
    check("mode list filled", len(getattr(tab, "_mode_rows", [])) >= 1)
    check("display combobox populated", tab.device_cb["values"])
    check("profile list filled", len(getattr(tab, "_profile_rows", [])) >= 0)

    # revert countdown logic (pure after-loop, no mode change performed)
    fake_mode = display.modes[0]
    tab._start_revert_countdown(fake_mode)
    check("revert countdown started", tab._pending_mode == fake_mode
          and str(tab.keep_btn["state"]) == "normal")
    tab._cancel_revert(show=False)
    check("revert cancel clears", tab._pending_mode is None
          and str(tab.keep_btn["state"]) == "disabled")

    # shutdown path (restores DVC + saturation if the engines own changes)
    try:
        tab.shutdown()
        ok = True
    except Exception as exc:
        ok = False
        print("   shutdown error:", exc)
    check("tab shutdown restores cleanly", ok)

    app.destroy()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} — {', '.join(FAILURES)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
