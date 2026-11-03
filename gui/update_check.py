"""Valtix GUI — check-only update checker.

Faithful to the Local Edition rule: Valtix never downloads or replaces code
on its own. With UPDATE_REPO set (e.g. "owner/repo"), it queries the latest
GitHub release and *reports* whether it is newer than the running VERSION.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

VERSION_PATH = Path(__file__).resolve().parents[1] / "VERSION"


def current_version() -> str:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _parse(ver: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", ver or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def check_for_update(repo: str | None = None, timeout: float = 6.0) -> dict:
    repo = (repo or os.getenv("UPDATE_REPO", "")).strip()
    if not repo or not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo):
        return {"status": "no_repo",
                "message": "No update source configured. Set UPDATE_REPO "
                           "(e.g. owner/repo) in .env — Valtix never "
                           "downloads code on its own."}
    try:
        import requests
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        tag = (resp.json() or {}).get("tag_name") or ""
        latest = tag.lstrip("vV")
        mine = current_version()
        if _parse(latest) > _parse(mine):
            return {"status": "update_available",
                    "message": f"Update available: v{latest} (you have v{mine}). "
                               f"Download it yourself from "
                               f"https://github.com/{repo}/releases — Valtix "
                               f"never replaces its own code.",
                    "latest": latest}
        return {"status": "up_to_date",
                "message": f"Valtix v{mine} is up to date."}
    except Exception as e:
        return {"status": "error", "message": f"Update check failed: {e}"}
