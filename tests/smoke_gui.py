"""GUI instantiation smoke test: builds the app window off-screen, pumps a
demo board through every tab, then destroys it. No mainloop block.

Run:  python -I tests/smoke_gui.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["DATA_SOURCE"] = "demo"
os.environ["VALTIX_QUIET"] = "1"

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("Sightware GUI — window smoke test (demo mode)\n")
    from gui.app import SightwareApp

    app = SightwareApp()
    app.withdraw()  # never flash a window during the test

    def pump(times: int = 8) -> None:
        # time-aware: let after() timers (queue drain etc.) actually expire
        end = time.time() + times * 0.03
        while time.time() < end:
            app.update_idletasks()
            app.update()
            time.sleep(0.01)

    pump(12)
    check("app constructed", True)

    for tab_key in ("live", "performance", "encounters", "sessions",
                    "inventory", "crosshair", "display"):
        try:
            app.show_tab(tab_key)
            pump(12)
            tab = app._tab_cache[tab_key]
            if tab_key == "performance":
                for _ in range(40):
                    app.update()
                    if getattr(tab, "_loaded_once", False):
                        break
                pump(6)
            if tab_key == "encounters":
                for _ in range(40):
                    app.update()
                    if getattr(tab, "_loaded_once", False):
                        break
                pump(6)
            if tab_key == "inventory":
                for _ in range(40):
                    app.update()
                    if getattr(tab, "_loaded_once", False):
                        break
                pump(6)
            check(f"tab {tab_key} renders", True)
        except Exception as e:
            check(f"tab {tab_key} renders", False, repr(e))

    # live board render with demo data
    try:
        board = app.core.live_board()
        live = app._tab_cache["live"]
        app.show_tab("live")
        live.update_board(board)
        pump(10)
        check("live board painted", len(live.team_table.rows()) > 0,
              "no team rows")
        check("final scoreboard painted",
              len(live.fs_table.rows()) > 0, "no fs rows")
    except Exception as e:
        check("live board painted", False, repr(e))

    # dialogs
    from gui.dialogs import SettingsDialog, PrivacyDialog, MatchDetailDialog
    fs = board.get("finalScoreboard") or {}
    match_id = fs.get("matchId")
    for name, factory in (
            ("settings", lambda: SettingsDialog(app)),
            ("privacy", lambda: PrivacyDialog(app)),
            ("match detail", lambda: MatchDetailDialog(
                app, match_id, subject=board.get("selfPuuid")))):
        try:
            dlg = factory()
            for _ in range(12):
                app.update_idletasks()
                app.update()
            dlg.destroy()
            pump(4)
            check(f"dialog {name} opens", True)
        except Exception as e:
            check(f"dialog {name} opens", False, repr(e))

    app._on_close()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("All GUI smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
