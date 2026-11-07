from __future__ import annotations

import threading
import time

import settings
from agents import resolve_agent
from quicklock import preferred_for_map
from riot_client import LocalAuth
from vconstants import map_name_from_path

_ACTIVE_SINCE: dict = {"state": None, "since": 0.0}
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()

_STATUS: dict = {
    "running": False,
    "observing": False,
    "state": None,
    "map": None,
    "preferred": None,
    "rec": None,
    "notice": "",
}

POLL_ACTIVE_S = 2.5
POLL_IDLE_S = 15.0


def status() -> dict:
    with _LOCK:
        return dict(_STATUS)


def _set(**kw) -> None:
    with _LOCK:
        _STATUS.update(**kw)


def snapshot_for_board() -> dict:
    st = status()
    return {
        "assistant": {
            "enabled": st["observing"],
            "state": st["state"],
            "map": st["map"],
            "preferred": st["preferred"],
            "rec": st["rec"],
            "preferredMeta": (resolve_agent(st["preferred"]) or {}),
            "notice": st["notice"],
        }
    }


_AUTH: LocalAuth | None = None


def _get_auth() -> LocalAuth | None:
    global _AUTH
    if not LocalAuth.available():
        _AUTH = None
        return None
    if _AUTH is None:
        try:
            _AUTH = LocalAuth()
            _AUTH.headers()
        except Exception:
            _AUTH = None
    return _AUTH


def reset_auth() -> None:
    global _AUTH
    _AUTH = None


def _observe_once() -> float:
    if not settings.get("assistantEnabled"):
        _set(observing=False, state=None, preferred=None, map=None,
             notice="Assistant is off.")
        return POLL_IDLE_S
    _set(observing=True)

    auth = _get_auth()
    if auth is None:
        _set(state="OFFLINE", map=None, preferred=None,
             notice="VALORANT isn't running — assistant is idle.")
        return POLL_IDLE_S

    try:
        presences = auth.local_get("/chat/v4/presences").get("presences") or []
    except Exception:
        reset_auth()
        _set(state="OFFLINE", map=None, preferred=None,
             notice="VALORANT isn't running — assistant is idle.")
        return POLL_IDLE_S

    state = "OFFLINE"
    for p in presences:
        if p.get("puuid") != auth.puuid:
            continue
        if p.get("product") not in (None, "", "valorant"):
            continue
        import base64, json as _json
        try:
            priv = _json.loads(
                base64.b64decode(str(p.get("private") or "")).decode("utf-8"))
        except Exception:
            priv = {}
        data = priv.get("matchPresenceData", priv)
        state = data.get("sessionLoopState",
                         priv.get("sessionLoopState", "MENUS"))
        break

    if state != _ACTIVE_SINCE["state"]:
        _ACTIVE_SINCE.update(state=state, since=time.time())

    if state == "PREGAME":
        map_name = None
        try:
            pg = auth.glz_get(f"/pregame/v1/players/{auth.puuid}")
            mid = pg.get("MatchID") if isinstance(pg, dict) else None
            if mid:
                match = auth.glz_get(f"/pregame/v1/matches/{mid}")
                map_name = map_name_from_path((match or {}).get("MapID", ""))
        except Exception:
            map_name = None
        pref = preferred_for_map(map_name)
        rec = None
        if pref is None:
            try:
                import pick_advisor
                import history
                rec = pick_advisor.recommend(
                    history.payload(auth.puuid).get("points") or []
                ).get("agent")
            except Exception:
                rec = None
        _set(state=state, map=map_name, preferred=pref, rec=rec,
             notice=(f"Agent Select on {map_name or 'Unknown'}. Your pick: "
                     f"{pref or rec or '—'} — lock it in game, or pick an "
                     f"agent and press INSTA-LOCK (if it is enabled)."))
        return POLL_ACTIVE_S

    _set(state=state, map=None, preferred=None,
         notice="" if state == "INGAME" else "Waiting for agent select…")
    return POLL_ACTIVE_S


_RUN_ID = 0


def _run(run_id: int) -> None:
    while _RUN_ID == run_id and not _STOP.is_set():
        delay = _observe_once()
        _STOP.wait(delay)


def start() -> None:
    global _THREAD, _RUN_ID
    # a new run id retires any previous thread without waiting for it —
    # the old code bailed out while the old thread was still draining,
    # leaving the assistant dead after an off→on settings toggle
    _RUN_ID += 1
    _STOP.clear()
    _THREAD = threading.Thread(target=_run, args=(_RUN_ID,),
                               name="sightware-assistant", daemon=True)
    _THREAD.start()


def stop() -> None:
    global _RUN_ID
    _RUN_ID += 1
    _STOP.set()
