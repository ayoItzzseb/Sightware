from __future__ import annotations

import threading
import time

import settings
from agents import resolve_agent
from riot_client import LocalAuth
from vconstants import map_name_from_path

_LOCK = threading.Lock()
_LAST = {"at": 0.0, "ok": False, "message": "No lock attempted yet.",
         "agent": None, "map": None, "status": "idle"}

_MIN_INTERVAL_S = 1.5
_ATTEMPT_AT = 0.0


def status() -> dict:
    with _LOCK:
        return dict(_LAST)


def _remember(ok: bool, status: str, message: str, agent: str | None,
              map_name: str | None) -> dict:
    with _LOCK:
        _LAST.update(at=time.time(), ok=ok, status=status, message=message,
                     agent=agent, map=map_name)
        return dict(_LAST)


def preferred_for_map(map_name: str | None) -> str | None:
    per_map = settings.get("perMap") or {}
    if map_name:
        hit = per_map.get(str(map_name).strip())
        if hit and resolve_agent(hit):
            return hit
    if settings.get("rememberAgent"):
        agent = settings.get("preferredAgent")
        if agent and resolve_agent(agent):
            return agent
    return None


def lock_now(agent_identifier: str | None = None,
             mode: str = "lock") -> dict:
    if not settings.quick_lock_allowed():
        return _remember(
            False, "disabled",
            "Insta-Lock is disabled — turn it on in Settings (and confirm the "
            "policy notice) if you want it.", None, None)

    agent = resolve_agent(agent_identifier or preferred_for_map(None) or "")
    if not agent:
        return _remember(False, "error",
                         "No agent chosen. Pick one first.", None, None)
    if mode not in ("lock", "hover"):
        mode = "lock"

    global _ATTEMPT_AT
    with _LOCK:
        now = time.time()
        if now - _ATTEMPT_AT < _MIN_INTERVAL_S:
            busy = True
        else:
            busy = False
            _ATTEMPT_AT = now
    if busy:
        return _remember(False, "busy",
                         "You just pressed it — wait a moment.",
                         agent["name"], None)

    try:
        auth = LocalAuth(settings.get("region") if settings.get("region") != "auto" else None)
        auth.headers()
    except Exception as e:
        return _remember(False, "error",
                         f"Couldn't reach the local VALORANT client: {e}",
                         agent["name"], None)

    try:
        pre = auth.glz_get(f"/pregame/v1/players/{auth.puuid}")
        match_id = pre.get("MatchID") if isinstance(pre, dict) else None
        if not match_id:
            return _remember(False, "not_in_select",
                             "You're not in agent select.", agent["name"], None)

        match = auth.glz_get(f"/pregame/v1/matches/{match_id}")
        map_name = map_name_from_path((match or {}).get("MapID", ""))

        chosen = agent
        if agent_identifier is None:
            pref = preferred_for_map(map_name)
            resolved = resolve_agent(pref or "")
            if resolved:
                chosen = resolved

        r = auth.glz_post(
            f"/pregame/v1/matches/{match_id}/select/{chosen['uuid']}")
        if mode == "lock" and r.status_code < 400:
            r = auth.glz_post(
                f"/pregame/v1/matches/{match_id}/lock/{chosen['uuid']}")
        if r.status_code >= 400:
            return _remember(
                False, "refused",
                f"Riot refused {chosen['name']} (HTTP {r.status_code}) — "
                f"pick manually.", chosen["name"], map_name)

        if settings.get("rememberAgent"):
            settings.update({"preferredAgent": chosen["name"]})

        msg = f"{'Locked' if mode == 'lock' else 'Hovered'} {chosen['name']}"
        if map_name and map_name != "Unknown":
            msg += f" on {map_name}"
        return _remember(True, "locked" if mode == "lock" else "hovered",
                         msg, chosen["name"], map_name)
    except Exception as e:
        return _remember(False, "error", f"Lock failed: {e}",
                         agent["name"], None)
