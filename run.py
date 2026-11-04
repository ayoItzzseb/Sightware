"""Sightware — GUI Edition launcher.

Replaces the v2.5.8 Flask/terminal launcher with a single native desktop
app. No web server, no browser — the tkinter window is the whole UI.

Usage:
    python run.py              # launch the GUI
    python run.py --console    # keep the console window open (debugging)
    python run.py --demo       # force demo data (no client needed)
    python run.py --once       # print one live board to the terminal and exit
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # PyInstaller build: keep data & logs next to the exe, not in the
    # ephemeral _MEIPASS bundle dir.
    ROOT = Path(sys.executable).resolve().parent
    os.environ.setdefault("VALTIX_DATA_DIR", str(ROOT / "data"))
    os.environ.setdefault("SIGHTWARE_LOG_DIR", str(ROOT / "logs"))
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

IS_WIN = os.name == "nt"


def _hide_console() -> None:
    """Hide the launching console (matches v2.5.5's 'no console' behavior)."""
    if not IS_WIN or "--console" in sys.argv:
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def _single_instance() -> None:
    if not IS_WIN:
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                     wintypes.LPCWSTR)
        k32.CreateMutexW(None, False, "SightwareGuiSingleInstanceMutex")
        if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print("Sightware is already running.", flush=True)
            sys.exit(0)
    except Exception:
        pass


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = sys.argv[1:]
    if "--demo" in args and "DATA_SOURCE" not in os.environ:
        os.environ["DATA_SOURCE"] = "demo"
    os.environ.setdefault("VALTIX_QUIET", "1")

    try:
        import requests  # noqa: F401
        import tzdata  # noqa: F401
    except ImportError as e:
        print(f"Sightware is missing a dependency ({e.name}).\n"
              f"Run install.bat (or: python -m pip install -r requirements.txt).")
        sys.exit(1)

    if "--once" in args and not getattr(sys, "frozen", False):
        # terminal scoreboard, single shot (the classic CLI view).
        # Not available from the windowed .exe — there is no console there.
        _once()
        return

    _single_instance()
    _hide_console()

    from gui.app import run
    run()


def _once() -> None:
    """Print one scoreboard in the terminal, then exit (rich if available)."""
    from gui.core import AppCore
    core = AppCore()
    board = core.live_board()
    state = board.get("stateLabel", "—")
    print(f"\nSightware — {state} · {board.get('map', '—')} "
          f"{('· ' + board['mode']) if board.get('mode') else ''} "
          f"[{board.get('source', '?')}]")
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(box=None, header_style="bold", pad_edge=False)
        for col in ("Agent", "Name", "Rank", "Peak", "Lvl", "K/D", "HS%", "WR%"):
            table.add_column(col)
        for team, players in (board.get("teams") or {}).items():
            for p in players:
                kd = p.get("kd")
                table.add_row(
                    p.get("agent") or "—", p.get("name") or "—",
                    p.get("rank") or "—", p.get("peakRank") or "—",
                    str(p.get("level") or "—"),
                    f"{kd:.2f}" if kd is not None else "…",
                    f"{p.get('hsPct')}%" if p.get("hsPct") is not None else "—",
                    f"{p.get('winRate')}%" if p.get("winRate") is not None else "—")
        console.print(table)
    except ImportError:
        for team, players in (board.get("teams") or {}).items():
            for p in players:
                kd = p.get("kd")
                print(f"  {p.get('agent') or '—':<12} {p.get('name') or '—':<24} "
                      f"{p.get('rank') or '—':<14} lvl {p.get('level') or '—'} "
                      f"KD {f'{kd:.2f}' if kd is not None else '…'}")
    print("\n(launch without --once for the full GUI)")


if __name__ == "__main__":
    main()
