from __future__ import annotations

import json
import os
import threading

from agents import resolve_agent
from vconstants import MAPS

_DATA_DIR = os.environ.get("VALTIX_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_PATH = os.path.join(_DATA_DIR, "settings.json")
_LOCK = threading.RLock()

REGIONS = ["na", "eu", "ap", "kr", "latam", "br"]

DEFAULTS = {
    "region": "auto",
    "assistantEnabled": True,
    "assistantAutoStart": True,
    "quickLockEnabled": False,
    "quickLockPolicyAck": False,
    "rememberAgent": True,
    "preferredAgent": None,
    "perMap": {},
    "dashboardEnabled": True,
    "openDashboardOnLaunch": True,
    "hideTerminalOnLaunch": True,
    "localHistoryEnabled": True,
    "includeLiveStats": True,
    "loadArt": True,
    "autoUpdates": False,
    "soundAlerts": True,
    "startWithWindows": False,
    "windowGeometry": "",
    "lastTab": "",
}

_BOOL_KEYS = {k for k, v in DEFAULTS.items() if isinstance(v, bool)}


def _coerce(key: str, value):
    default = DEFAULTS.get(key)
    if key in _BOOL_KEYS:
        return value if isinstance(value, bool) else default
    if key == "region":
        value = str(value or "auto").strip().lower()
        return value if value in ("auto", *REGIONS) else "auto"
    if key == "perMap":
        out: dict[str, str] = {}
        if isinstance(value, dict):
            for map_name, agent in value.items():
                m = str(map_name or "").strip()
                a = resolve_agent(str(agent or ""))
                if m in MAPS and a:
                    out[m] = a["name"]
        return out
    if key == "preferredAgent":
        if value in (None, ""):
            return None
        agent = resolve_agent(str(value))
        return agent["name"] if agent else None
    if key == "includeLiveStats":
        return value if isinstance(value, bool) else DEFAULTS["includeLiveStats"]
    return value if value is None or isinstance(value, type(default)) else default


def _load_raw() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _migrate(raw: dict) -> dict:
    out = dict(raw)
    if "dryRun" in raw:
        out["quickLockPolicyAck"] = bool(raw.get("quickLockPolicyAck", False))
        out.pop("dryRun", None)
    if "agent" in raw:
        out.setdefault("preferredAgent", raw.get("agent"))
        out.pop("agent", None)
    if "perMap" in raw and not isinstance(raw.get("perMap"), dict):
        out.pop("perMap", None)
    for legacy in ("mode", "delay", "autoRefresh", "remoteMode",
                   "discordRpc", "telemetry", "appearOffline",
                   "instalockEnabled", "instalockPolicyAck",
                   "instalockAgent"):
        out.pop(legacy, None)
    return out


def all_settings() -> dict:
    with _LOCK:
        raw = _migrate(_load_raw())
        out = {}
        for key, default in DEFAULTS.items():
            out[key] = _coerce(key, raw.get(key, default)) if key in raw else default
        return out


def get(key: str):
    if key not in DEFAULTS:
        raise KeyError(key)
    with _LOCK:
        raw = _migrate(_load_raw())
        if key not in raw:
            return DEFAULTS[key]
        return _coerce(key, raw[key])


def update(incoming: dict) -> dict:
    clean = {k: v for k, v in (incoming or {}).items() if k in DEFAULTS}
    with _LOCK:
        merged = all_settings()
        for key, value in clean.items():
            merged[key] = _coerce(key, value)
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = f"{_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, _PATH)
        return merged


def quick_lock_allowed() -> bool:
    return bool(get("quickLockEnabled")) and bool(get("quickLockPolicyAck"))
