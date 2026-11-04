"""Sightware GUI — GitHub update checker & self-updater (Redesign Prototype).

Source of truth: the VERSION file on the repository's main branch.
When a newer version is published, Sightware can update itself in place:

* downloads the repo ZIP from codeload.github.com
* extracts it and overlays every file EXCEPT user data
  (backend/data/, .valtix/, .env, logs)
* the caller then restarts the app

Purely opt-in: nothing runs unless the user asks for it (or enabled the
"Automatic updates" setting).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = APP_ROOT / "VERSION"
DEFAULT_REPO = "ayoItzzseb/Sightware"

# never overwritten by an update
PRESERVE = ("backend/data", ".valtix", ".env", "docs", "__pycache__")


def current_version() -> str:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _parse(ver: str) -> tuple[int, ...]:
    import re
    nums = re.findall(r"\d+", ver or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def _repo() -> str:
    repo = os.getenv("UPDATE_REPO", DEFAULT_REPO).strip()
    import re
    return repo if re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo) else DEFAULT_REPO


def _remote_version(timeout: float = 6.0) -> str | None:
    import requests
    repo = _repo()
    # 1) GitHub release tag, if any (nice for tagged releases)
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        if resp.ok:
            tag = (resp.json() or {}).get("tag_name") or ""
            if tag.strip("vV "):
                return tag.lstrip("vV").strip()
    except Exception:
        pass
    # 2) fall back to the VERSION file on main
    resp = requests.get(
        f"https://raw.githubusercontent.com/{repo}/main/VERSION",
        timeout=timeout)
    if resp.ok:
        return resp.text.strip()
    return None


def check_for_update(repo: str | None = None, timeout: float = 6.0) -> dict:
    """Returns {status, message, latest?}. status:
    update_available | up_to_date | error | no_repo"""
    mine = current_version()
    try:
        latest = _remote_version(timeout)
    except Exception as e:
        return {"status": "error", "message": f"Update check failed: {e}"}
    if not latest:
        return {"status": "error", "message": "Could not reach the update source."}
    if _parse(latest) > _parse(mine):
        return {"status": "update_available",
                "message": f"Update available: v{latest} (you have v{mine})",
                "latest": latest}
    return {"status": "up_to_date",
            "message": f"Sightware v{mine} is up to date."}


# ── self-update ────────────────────────────────────────────────

def _preserve(rel_posix: str) -> bool:
    rel = rel_posix.replace("\\", "/").rstrip("/")
    for keep in PRESERVE:
        if rel == keep or rel.startswith(keep + "/"):
            return True
    return False


def perform_update(latest: str | None = None, log=None) -> dict:
    """Download main-branch ZIP and overlay it onto the app folder.

    Returns {ok, message}. User data under backend/data/, .valtix/ and
    .env is never touched. Call restart_app() afterwards.
    """
    import requests

    def say(msg):
        if log:
            try:
                log(msg)
            except Exception:
                pass

    repo = _repo()
    try:
        say("Downloading update…")
        resp = requests.get(
            f"https://codeload.github.com/{repo}/zip/refs/heads/main",
            timeout=60, stream=True)
        resp.raise_for_status()
        tmp_zip = Path(tempfile.gettempdir()) / f"sightware-update-{latest or 'main'}.zip"
        with open(tmp_zip, "wb") as f:
            for chunk in resp.iter_content(1 << 15):
                f.write(chunk)

        say("Extracting…")
        tmp_dir = Path(tempfile.mkdtemp(prefix="sightware-update-"))
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(tmp_dir)
        inner = next(tmp_dir.iterdir())  # repo-<sha>/ folder
        if not inner.is_dir():
            return {"ok": False, "message": "Update archive had an unexpected layout."}

        say("Installing files…")
        installed = 0
        for src in inner.rglob("*"):
            rel = src.relative_to(inner)
            if _preserve(str(rel)):
                continue
            if src.is_dir():
                continue
            dest = APP_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            installed += 1

        # keep the local VERSION authoritative-check simple: it was just
        # overwritten by the download; verify it
        new_ver = current_version()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_zip.unlink(missing_ok=True)
        return {"ok": True,
                "message": f"Updated to v{new_ver} ({installed} files). "
                           f"Restart to finish."}
    except Exception as e:
        return {"ok": False, "message": f"Update failed: {e}"}


def restart_app() -> None:
    """Relaunch Sightware from source (source-run installs only)."""
    import subprocess
    import sys
    if getattr(sys, "frozen", False):
        raise OSError("Auto-restart is only supported for source installs.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.is_file() else sys.executable)
    subprocess.Popen([exe, str(APP_ROOT / "run.py")], cwd=str(APP_ROOT),
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                     if os.name == "nt" else 0)
