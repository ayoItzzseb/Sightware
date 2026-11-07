"""Sightware — career advanced-stats cache.

Enriches stored match points with the deep stats only available from
match detail payloads (ADR, headshot %, first bloods/deaths, multikills,
aces). Everything is cached locally in backend/data/career-stats.json and
refreshed opportunistically while the Riot client is open (local API only —
no internet traffic, no game interaction).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time

_DATA_DIR = (os.environ.get("VALTIX_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data"))
_PATH = os.path.join(_DATA_DIR, "career-stats.json")
_LOCK = threading.RLock()

# how many un-cached matches one enrichment pass may fetch (local API, be gentle)
BATCH = 10
_RETRY_AFTER = 3600  # seconds before re-trying a match that failed


def _load() -> dict | None:
    """None = unreadable (callers must not save over it); {} = no cache yet."""
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return None


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_PATH), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def stats_for(match_id: str) -> dict | None:
    with _LOCK:
        return ((_load() or {}).get("matches") or {}).get(match_id)


def aggregate(points: list[dict]) -> dict:
    """Career aggregates over the matches in the current window that have
    cached deep stats. Iterates the points (one account's match list), not
    the whole cache, so multi-account stores can't bleed across tabs."""
    matches = (_load() or {}).get("matches") or {}
    rows = []
    for p in points or []:
        st = matches.get(p.get("matchId"))
        if not st:
            continue
        rows.append({
            "matchId": mid,
            "ts": p.get("ts") or st.get("ts"),
            "agent": p.get("agent") or st.get("agent"),
            "map": p.get("map") or st.get("map"),
            "result": p.get("result") or st.get("result"),
            "adr": st.get("adr"),
            "hsPct": st.get("hsPct"),
            "firstBloods": st.get("firstBloods"),
            "firstDeaths": st.get("firstDeaths"),
            "multiKills": st.get("multiKills"),
            "aces": st.get("aces"),
            "kd": st.get("kd") or p.get("kd"),
        })
    rows = [r for r in rows if r["ts"]]
    rows.sort(key=lambda r: r["ts"] or 0)
    out = {"matches": len(rows), "rows": rows[-25:]}

    def avg(key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 2) if vals else None

    out["avgAdr"] = avg("adr")
    out["avgHsPct"] = avg("hsPct")
    out["fbPerMatch"] = round(sum(r["firstBloods"] or 0 for r in rows
                                  if isinstance(r.get("firstBloods"), (int, float)))
                              / len(rows), 2) if rows else None
    out["fdPerMatch"] = round(sum(r["firstDeaths"] or 0 for r in rows
                                  if isinstance(r.get("firstDeaths"), (int, float)))
                              / len(rows), 2) if rows else None
    out["multiKills"] = sum(r["multiKills"] or 0 for r in rows
                            if isinstance(r.get("multiKills"), (int, float)))
    out["aces"] = sum(r["aces"] or 0 for r in rows
                      if isinstance(r.get("aces"), (int, float)))
    fb = sum(r["firstBloods"] or 0 for r in rows if isinstance(r.get("firstBloods"), (int, float)))
    fd = sum(r["firstDeaths"] or 0 for r in rows if isinstance(r.get("firstDeaths"), (int, float)))
    out["fbRatio"] = round(fb / fd, 2) if fd else (None if not fb else round(fb, 2))
    return out


def enrich(core, points: list[dict], limit: int = BATCH, log=None,
           self_puuid: str | None = None) -> dict:
    """Fetch deep stats for stored matches that lack them. Works only while
    the local Riot client can serve match details. Returns progress info."""
    data = _load()
    if data is None:
        # cache file unreadable (AV lock, disk issue) — abort instead of
        # starting from {} and overwriting the whole store on the next save
        return {"done": 0, "failed": 0, "remaining": len(points or []),
                "cached": 0, "error": "career-stats cache unreadable"}
    matches = data.setdefault("matches", {})
    tries = data.setdefault("tries", {})
    now = time.time()
    todo = [p for p in points or []
            if p.get("matchId") and p["matchId"] not in matches
            and now - tries.get(p["matchId"], 0) > _RETRY_AFTER]
    done = failed = 0
    for point in todo[:max(1, limit)]:
        mid = point["matchId"]
        if log:
            log(f"Enriching match {done + 1}/{min(len(todo), limit)}…")
        try:
            detail = core.match_detail(mid)
        except Exception:
            detail = {"error": "failed"}
        if detail.get("error"):
            tries[mid] = now
            failed += 1
            continue
        me = next((pl for pl in detail.get("players", [])
                   if pl.get("isSubject")
                   or pl.get("puuid") == (self_puuid or "")), None)
        if not me:
            tries[mid] = now
            failed += 1
            continue
        matches[mid] = {
            "ts": point.get("ts"),
            "agent": point.get("agent"),
            "map": point.get("map"),
            "result": point.get("result"),
            "rounds": detail.get("rounds"),
            "kills": me.get("kills"), "deaths": me.get("deaths"),
            "assists": me.get("assists"),
            "adr": me.get("adr"), "hsPct": me.get("hsPct"),
            "firstBloods": me.get("firstBloods"),
            "firstDeaths": me.get("firstDeaths"),
            "multiKills": me.get("multiKills"), "aces": me.get("aces"),
        }
        done += 1
        _save(data)  # incremental save so a crash never loses progress
    with _LOCK:
        cached = len((_load() or {}).get("matches") or {})
    return {"done": done, "failed": failed, "remaining": max(0, len(todo) - done),
            "cached": cached}
