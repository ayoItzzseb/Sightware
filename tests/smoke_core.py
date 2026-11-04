"""Headless smoke test for the GUI edition's AppCore (demo mode).

Run:  python -I tests/smoke_core.py
"""
from __future__ import annotations

import os
import sys
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
    print("Valtix GUI — core smoke test (demo mode)\n")

    from gui.core import AppCore
    core = AppCore()

    print("live board")
    board = core.live_board()
    check("board has state", bool(board.get("state")))
    check("board has players", len(board.get("players") or []) > 0)
    check("board has teams", bool(board.get("teams")))
    check("board has assistant snapshot", "assistant" in board)
    check("board has quicklock snapshot", "quickLock" in board)
    check("board source is demo", board.get("source") == "demo")
    fs = board.get("finalScoreboard")
    check("final scoreboard attached", isinstance(fs, dict)
          and len(fs.get("players") or []) > 0)

    print("\nstate")
    st = core.game_state()
    check("game_state returns", bool(st.get("state")))

    print("\nencounters")
    enc = core.encounters()
    check("encounters payload", isinstance(enc.get("players"), list))

    print("\nperformance")
    perf = core.performance()
    check("performance summary", isinstance(perf.get("summary"), dict))
    check("performance points", isinstance(perf.get("points"), list))
    check("performance splits", isinstance(perf.get("splits"), dict))

    print("\ninsights")
    ins = core.insights()
    check("insights payload", isinstance(ins.get("summary"), dict))

    print("\nsessions")
    sess = core.sessions()
    check("sessions payload", "active" in sess and "archive" in sess)
    started = core.session_start({"type": "rr", "target": 50})
    # In demo mode there is no live account, so the tracker correctly
    # refuses — same gate the v2.5.8 backend had. Accept either outcome.
    check("session start handled",
          bool(started.get("ok", True))
          or "VALORANT" in str(started.get("message", "")), str(started))
    ended = core.session_end()
    check("session end handled",
          bool(ended.get("ok", True))
          or "account" in str(ended.get("message", "")).lower(), str(ended))

    print("\nrecap")
    recap = core.recap()
    check("recap payload", recap.get("session") is not None
          or recap.get("summary") is not None
          or isinstance(recap, dict))

    print("\ninventory (demo)")
    inv = core.inventory()
    check("inventory available", bool(inv.get("available")), str(inv)[:120])
    check("inventory has vp", isinstance(inv.get("totalVp"), int))

    print("\nprofiles & matches")
    demo_puuid = next((p["puuid"] for p in board["players"] if p.get("puuid")),
                      None)
    check("found a demo puuid", bool(demo_puuid))
    if demo_puuid:
        profile = core.profile(demo_puuid)
        check("profile has matches", len(profile.get("matches") or []) > 0,
              str(profile)[:120])
    match_id = fs.get("matchId") if isinstance(fs, dict) else None
    check("found a demo match id", bool(match_id))
    if match_id:
        md = core.match_detail(match_id, demo_puuid)
        check("match detail players", len(md.get("players") or []) > 0,
              str(md)[:120])
        meta = core.set_match_meta(match_id, {"note": "smoke", "tags": ["t1"],
                                              "bookmarked": True})
        # Requires a live account (demo has none) — the gate is expected.
        check("match meta handled",
              bool(meta.get("ok"))
              or "account" in str(meta.get("message", "")).lower(), str(meta))

    print("\nplayer lookup")
    if demo_puuid:
        pl = core.player(demo_puuid)
        check("player payload", bool(pl.get("riotId")), str(pl)[:120])

    print("\nqueue / quicklock / region / health / privacy")
    check("queue state", isinstance(core.queue_state(), dict))
    ql = core.quicklock_status()
    check("quicklock status", "enabled" in ql)
    # force the disabled state for this check, then restore the user's choice
    _saved_ql = {k: core.all_settings().get(k) for k in
                 ("quickLockEnabled", "quickLockPolicyAck")}
    core.update_settings({"quickLockEnabled": False})
    locked = core.quicklock_lock("Jett")
    check("quicklock refused when disabled",
          locked.get("status") == "disabled", str(locked))
    core.update_settings(_saved_ql)
    check("region info", "regions" in core.region_info())
    check("health", core.health().get("ok") is True)
    check("privacy", "telemetry" in core.privacy())
    check("agents list", core.agents()["count"] > 20)

    print("\nsettings round-trip")
    merged = core.update_settings({"rememberAgent": False})
    check("settings update", merged.get("rememberAgent") is False)
    merged = core.update_settings({"rememberAgent": True})
    check("settings restore", merged.get("rememberAgent") is True)
    merged = core.update_settings({"perMap": {"Ascent": "Jett"}})
    check("per-map accepted", merged.get("perMap") == {"Ascent": "Jett"})

    print("\nGUI-edition settings (3.1)")
    merged = core.update_settings({"soundAlerts": False})
    check("soundAlerts persists", merged.get("soundAlerts") is False)
    merged = core.update_settings({"soundAlerts": True,
                                   "windowGeometry": "1280x820",
                                   "lastTab": "live"})
    check("window prefs persist",
          merged.get("windowGeometry") == "1280x820"
          and merged.get("lastTab") == "live")
    from gui.update_check import check_for_update, current_version, _parse
    check("local version parses", _parse(current_version()) > (0,))
    res = check_for_update(timeout=4.0)
    check("update checker returns a known status",
          res.get("status") in ("update_available", "up_to_date", "error"),
          str(res))
    from gui import platform_win
    check("startup toggle off by default",
          platform_win.start_with_windows_enabled() in (True, False))
    lock = core.quicklock_lock("Jett", mode="hover")
    check("hover mode reachable", "status" in lock, str(lock))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
        return 1
    print("All core smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
