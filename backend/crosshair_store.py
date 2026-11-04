"""Crosshair Overlay — config & library storage.

Keeps everything under ``backend/data/crosshair/``:

* ``crosshair.json``  — the active crosshair (Simple Sight-compatible schema)
* ``overlay.json``    — hotkeys / ADS / display / whitelist settings
* ``library/*.json``  — saved crosshair presets (Simple Sight-compatible)
* ``library/custom/*.png`` — imported image crosshairs
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading

_LOCK = threading.RLock()

_DATA_DIR = (os.environ.get("VALTIX_DATA_DIR")
             or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
_BASE = os.path.join(_DATA_DIR, "crosshair")
_LIBRARY = os.path.join(_BASE, "library")
_CUSTOM = os.path.join(_BASE, "library", "custom")

CROSSHAIR_DEFAULT = {
    "crosshair": {
        "style": "cross",
        "gap": 2,
        "length": 4,
        "thickness": 2,
        "tint": "#FFFFFFFF",
        "lines": [True, True, True, True],
        "outline": {"thickness": 2, "tint": "#00000080"},
        "dot": {
            "style": "circle",
            "size": 0,
            "tint": "#FFFFFFFF",
            "outline": {"thickness": 0, "tint": "#000000FF"},
        },
    },
    "custom": {"path": "-", "filter": "linear", "scale": 1.0, "tint": "#FFFFFFFF"},
    "pixels": {"data": "", "scale": 1.0, "tint": "#FFFFFFFF"},
}

OVERLAY_DEFAULT = {
    "enabled": True,
    "targetDisplay": "primary",          # primary | all | <index>
    "offsetX": 0,
    "offsetY": 0,
    "scale": 1.0,
    "toggleKey": "F10",
    "toggleKey2": "",
    "enableAds": False,
    "adsAction": "hide",                 # hide | switch
    "adsBehaviour": "hold",              # hold | toggle
    "adsKey": "MOUSE RIGHT",
    "adsKey2": "",
    "adsPath": "",                       # library preset name for switch mode
    "gamepad": False,
    "whitelistEnabled": False,
    "whitelist": [],                     # [{"name": str, "path": str}]
    "quickload": [
        {"name": "Slot 1", "key": "F1", "crosshair": ""},
        {"name": "Slot 2", "key": "F2", "crosshair": ""},
        {"name": "Slot 3", "key": "F3", "crosshair": ""},
        {"name": "Slot 4", "key": "F4", "crosshair": ""},
    ],
}


def _ensure_dirs() -> None:
    first_run = not os.path.isdir(_LIBRARY)
    for p in (_BASE, _LIBRARY, _CUSTOM):
        if not os.path.isdir(p):
            os.makedirs(p, exist_ok=True)
    # library/custom lives inside library, so "empty" means no .json presets
    if first_run and not any(f.endswith(".json") for f in os.listdir(_LIBRARY)):
        _seed_presets()


# A few clean built-in presets so a fresh install has something to load.
# (Your own library and any Simple Sight import go in the same folder.)
_PRESET_SEEDS = {
    "Classic Cross": {
        "crosshair": {"style": "cross", "gap": 3, "length": 6, "thickness": 2,
                      "tint": "#00FF00FF", "lines": [True, True, True, True],
                      "outline": {"thickness": 2, "tint": "#000000FF"},
                      "dot": {"style": "circle", "size": 0, "tint": "#FFFFFFFF",
                              "outline": {"thickness": 0, "tint": "#000000FF"}}},
        "custom": {"path": "-", "filter": "linear", "scale": 1.0, "tint": "#FFFFFFFF"},
        "pixels": {"data": "", "scale": 1.0, "tint": "#FFFFFFFF"},
    },
    "White Dot": {
        "crosshair": {"style": "cross", "gap": 0, "length": 1, "thickness": 2,
                      "tint": "#FFFFFFFF", "lines": [False, False, False, False],
                      "outline": {"thickness": 2, "tint": "#000000FF"},
                      "dot": {"style": "circle", "size": 3, "tint": "#FFFFFFFF",
                              "outline": {"thickness": 2, "tint": "#000000FF"}}},
        "custom": {"path": "-", "filter": "linear", "scale": 1.0, "tint": "#FFFFFFFF"},
        "pixels": {"data": "", "scale": 1.0, "tint": "#FFFFFFFF"},
    },
    "Cyan Ring": {
        "crosshair": {"style": "circle", "gap": 8, "length": 1, "thickness": 2,
                      "tint": "#00E5FFFF", "lines": [True, True, True, True],
                      "outline": {"thickness": 2, "tint": "#000000FF"},
                      "dot": {"style": "circle", "size": 0, "tint": "#FFFFFFFF",
                              "outline": {"thickness": 0, "tint": "#000000FF"}}},
        "custom": {"path": "-", "filter": "linear", "scale": 1.0, "tint": "#FFFFFFFF"},
        "pixels": {"data": "", "scale": 1.0, "tint": "#FFFFFFFF"},
    },
}


def _seed_presets() -> None:
    for name, cfg in _PRESET_SEEDS.items():
        try:
            path = os.path.join(_LIBRARY, f"{name}.json")
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)
        except OSError:
            pass


def _read(path: str, default: dict) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _merge(data: dict, defaults: dict) -> dict:
    """Fill missing keys in place (shallow for dicts, recurse one level)."""
    for key, val in defaults.items():
        if key not in data:
            data[key] = json.loads(json.dumps(val))
        elif isinstance(val, dict) and isinstance(data[key], dict):
            _merge(data[key], val)
    return data


def _write(path: str, data: dict) -> None:
    with _LOCK:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)


# ── active crosshair ───────────────────────────────────────────

def get_crosshair() -> dict:
    _ensure_dirs()
    return _merge(_read(os.path.join(_BASE, "crosshair.json"), {}), CROSSHAIR_DEFAULT)


def save_crosshair(cfg: dict) -> None:
    _ensure_dirs()
    clean = json.loads(json.dumps(cfg))
    clean.get("crosshair", {}).pop("svg", None)
    clean.pop("imageData", None)
    _write(os.path.join(_BASE, "crosshair.json"), clean)


# ── overlay settings ───────────────────────────────────────────

def get_overlay_settings() -> dict:
    _ensure_dirs()
    return _merge(_read(os.path.join(_BASE, "overlay.json"), {}), OVERLAY_DEFAULT)


def save_overlay_settings(cfg: dict) -> dict:
    _ensure_dirs()
    merged = _merge(json.loads(json.dumps(cfg)), OVERLAY_DEFAULT)
    _write(os.path.join(_BASE, "overlay.json"), merged)
    return merged


# ── library ────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", str(name)).strip()[:80]


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def save_to_library(name: str, cfg: dict) -> str | None:
    _ensure_dirs()
    clean = _sanitize(name)
    if not clean:
        return None
    data = json.loads(json.dumps(cfg))
    data.get("crosshair", {}).pop("svg", None)
    data.pop("imageData", None)
    path = _unique(os.path.join(_LIBRARY, f"{clean}.json"))
    try:
        _write(path, data)
        return os.path.splitext(os.path.basename(path))[0]
    except OSError:
        return None


def delete_from_library(name: str) -> bool:
    path = os.path.join(_LIBRARY, f"{_sanitize(name)}.json")
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def rename_in_library(name: str, new_name: str) -> bool:
    clean = _sanitize(new_name)
    if not clean:
        return False
    src = os.path.join(_LIBRARY, f"{_sanitize(name)}.json")
    if not os.path.isfile(src):
        return False
    try:
        os.rename(src, _unique(os.path.join(_LIBRARY, f"{clean}.json")))
        return True
    except OSError:
        return False


def library_list() -> list[dict]:
    """[{name, config}] — broken files are skipped."""
    _ensure_dirs()
    out = []
    try:
        for fn in sorted(os.listdir(_LIBRARY)):
            if not fn.endswith(".json"):
                continue
            cfg = _merge(_read(os.path.join(_LIBRARY, fn), {}), CROSSHAIR_DEFAULT)
            out.append({"name": fn[:-5], "config": cfg})
    except OSError:
        pass
    return out


def load_from_library(name: str) -> dict | None:
    fn = _sanitize(name)
    path = os.path.join(_LIBRARY, f"{fn}.json")
    if os.path.isfile(path):
        return _merge(_read(path, {}), CROSSHAIR_DEFAULT)
    path = os.path.join(_CUSTOM, f"{fn}.png")
    if os.path.isfile(path):
        cfg = json.loads(json.dumps(CROSSHAIR_DEFAULT))
        cfg["crosshair"]["style"] = "custom"
        cfg["custom"]["path"] = f"{fn}.png"
        return cfg
    return None


def custom_list() -> list[dict]:
    """[{name, path}] of imported PNG crosshairs."""
    _ensure_dirs()
    out = []
    try:
        for fn in sorted(os.listdir(_CUSTOM)):
            if fn.endswith(".png"):
                out.append({"name": fn[:-4], "path": os.path.join(_CUSTOM, fn)})
    except OSError:
        pass
    return out


def import_pngs(paths: list[str]) -> int:
    _ensure_dirs()
    n = 0
    for src in paths:
        if not str(src).lower().endswith(".png"):
            continue
        try:
            shutil.copyfile(src, _unique(os.path.join(_CUSTOM, os.path.basename(src))))
            n += 1
        except OSError:
            pass
    return n


def custom_png_path(filename: str) -> str:
    return os.path.join(_CUSTOM, os.path.basename(str(filename)))


# ── one-click import from Simple Sight / Sightline ─────────────

_SIMPLE_SIGHT_GUESS = ("C:\\Program Files (x86)\\Steam\\steamapps\\common\\"
                       "Simple Sight - Crosshair Overlay\\library")
_SIGHTLINE_GUESS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "sightline", "data", "library")


def detect_import_dir() -> str | None:
    for guess in (_SIMPLE_SIGHT_GUESS, _SIGHTLINE_GUESS):
        if os.path.isdir(guess):
            return guess
    return None


def import_library(source_dir: str) -> dict:
    """Copy every preset + custom png from a Simple Sight-style library folder."""
    result = {"imported": 0, "skipped": 0, "errors": []}
    _ensure_dirs()
    try:
        for fn in sorted(os.listdir(source_dir)):
            if not fn.endswith(".json"):
                continue
            dest = os.path.join(_LIBRARY, fn)
            if os.path.exists(dest):
                result["skipped"] += 1
                continue
            try:
                shutil.copyfile(os.path.join(source_dir, fn), dest)
                result["imported"] += 1
            except OSError as e:
                result["errors"].append(f"{fn}: {e}")
        custom_src = os.path.join(source_dir, "custom")
        if os.path.isdir(custom_src):
            for fn in sorted(os.listdir(custom_src)):
                if not fn.endswith(".png"):
                    continue
                dest = os.path.join(_CUSTOM, fn)
                if os.path.exists(dest):
                    result["skipped"] += 1
                    continue
                try:
                    shutil.copyfile(os.path.join(custom_src, fn), dest)
                    result["imported"] += 1
                except OSError as e:
                    result["errors"].append(f"{fn}: {e}")
    except OSError as e:
        result["errors"].append(str(e))
    return result


# ── preset packs (share the whole library as one zip) ──────────

def export_pack(dest_path: str) -> dict:
    """Zip every library preset + custom png into dest_path."""
    import zipfile
    result = {"presets": 0, "images": 0}
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(_LIBRARY)):
            if fn.endswith(".json"):
                zf.write(os.path.join(_LIBRARY, fn), "library/" + fn)
                result["presets"] += 1
        if os.path.isdir(_CUSTOM):
            for fn in sorted(os.listdir(_CUSTOM)):
                if fn.endswith(".png"):
                    zf.write(os.path.join(_CUSTOM, fn), "library/custom/" + fn)
                    result["images"] += 1
    return result


def import_pack(src_path: str) -> dict:
    """Merge a preset-pack zip into the library. Existing files are skipped."""
    import zipfile
    result = {"presets": 0, "images": 0, "skipped": 0}
    _ensure_dirs()
    with zipfile.ZipFile(src_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("library/custom/") and name.endswith(".png"):
                dest = os.path.join(_CUSTOM, os.path.basename(name))
                if os.path.exists(dest):
                    result["skipped"] += 1
                    continue
                with zf.open(info) as fsrc, open(dest, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                result["images"] += 1
            elif name.startswith("library/") and name.endswith(".json"):
                dest = os.path.join(_LIBRARY, os.path.basename(name))
                if os.path.exists(dest):
                    result["skipped"] += 1
                    continue
                with zf.open(info) as fsrc, open(dest, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                result["presets"] += 1
    return result


# ── per-app crosshair memory ───────────────────────────────────

_PER_APP_FILE = os.path.join(_BASE, "per-app.json")


def get_per_app() -> dict:
    """{windowTitle: presetName} — crosshair switched in per whitelisted app."""
    return _read(_PER_APP_FILE, {}) or {}


def set_per_app(mapping: dict) -> None:
    _write(_PER_APP_FILE, mapping or {})
