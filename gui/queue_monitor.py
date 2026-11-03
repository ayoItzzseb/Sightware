"""Valtix GUI — queue monitor.

A light background thread that watches the party/queue snapshot (one cheap
glz read every few seconds while the client is live) and drives:
  • the status-bar queue strip (mode, party size, live queue timer)
  • the "queued" toast + sound on queue join
Match-found and match-end alerts fire from the board state transitions in
gui/app.py, which sees every fresh board already.
"""
from __future__ import annotations

import threading
import time

from riot_client import LocalAuth

POLL_ACTIVE_S = 3.0    # client running: keep the timer honest
POLL_IDLE_S = 15.0


def _fmt_elapsed(secs: float) -> str:
    secs = int(max(0, secs))
    return f"{secs // 60}:{secs % 60:02d}"


class QueueMonitor:
    def __init__(self, app):
        self.app = app
        self.core = app.core
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._prev_in_queue = False
        self._last_text = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="valtix-queue",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            delay = POLL_IDLE_S
            try:
                if LocalAuth.available() \
                        and self.core.client.source_pref != "demo":
                    snap = self.core.queue_state()
                    self.app._post_ui(lambda s=snap: self._apply(s))
                    delay = POLL_ACTIVE_S if snap.get("available") else POLL_IDLE_S
                else:
                    self.app._post_ui(lambda: self._apply(None))
            except Exception:
                pass
            self._stop.wait(delay)

    # ── UI updates (main thread) ───────────────────────────────
    def _apply(self, snap: dict | None) -> None:
        if self.app._shutting:
            return
        lbl = self.app.queue_lbl
        if not snap or not snap.get("available") or snap.get("demo"):
            if self._last_text:
                lbl.configure(text="")
                self._last_text = ""
            return
        bits = []
        size = snap.get("partySize") or 1
        if size > 1:
            bits.append(f"party {size}" +
                        ("" if snap.get("allReady", True) else " (ready check)"))
        if snap.get("inQueue"):
            elapsed = snap.get("queueElapsed")
            if elapsed is None and snap.get("queuedAt"):
                elapsed = max(0, time.time() - snap["queuedAt"])
            bits.append(f"in queue {_fmt_elapsed(elapsed or 0)}"
                        f" · {snap.get('queueName') or ''}")
            if not self._prev_in_queue:
                self._prev_in_queue = True
                self.app.notify("Queue joined — " +
                                (snap.get("queueName") or "matchmaking"),
                                kind="info", sound=True)
        else:
            self._prev_in_queue = False
        text = "  ·  ".join(b for b in bits if b)
        if text != self._last_text:
            lbl.configure(text=("⏱ " + text) if text else "")
            self._last_text = text
