"""Crosshair Overlay — global hotkeys, Vanguard-friendly.

Design notes (deliberately conservative for anti-cheat compatibility):

* NO ``SetWindowsHookEx`` hooks of any kind. Hooks inject into the input
  pipeline of every process on the desktop. Instead we passively poll
  ``GetAsyncKeyState`` from our own process — a documented, read-only query
  of system key state that every OS utility uses.
* NO ``OpenProcess`` / handles to other processes, no input synthesis
  (``SendInput`` etc.), no injection, no memory access.
* Gamepad support polls ``XInputGetState`` — our own controller hardware only.

Emits the same friendly key strings as the standalone Sightline app
("F1", "LEFT SHIFT + F2", "MOUSE RIGHT", "GP A"…) so existing configs fit.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time

# ── Windows bits ───────────────────────────────────────────────
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_xinput = None
for _xinput_dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_9.dll"):
    try:
        _xinput = ctypes.WinDLL(_xinput_dll)
        break
    except OSError:
        continue

GetAsyncKeyState = _user32.GetAsyncKeyState

VK_MODIFIERS = {
    0xA0: "LEFT SHIFT", 0xA1: "RIGHT SHIFT",
    0xA2: "LEFT CTRL", 0xA3: "RIGHT CTRL",
    0xA4: "LEFT ALT", 0xA5: "RIGHT ALT",
    0x5B: "LEFT WIN", 0x5C: "RIGHT WIN",
}
MOUSE_VKS = {0x01: "MOUSE LEFT", 0x02: "MOUSE RIGHT", 0x04: "MOUSE MIDDLE",
             0x05: "MOUSE X1", 0x06: "MOUSE X2"}
VK_NAMES = {
    0x08: "BACKSPACE", 0x09: "TAB", 0x0D: "ENTER", 0x13: "PAUSE", 0x14: "CAPS LOCK",
    0x1B: "ESCAPE", 0x20: "SPACE", 0x21: "PAGE UP", 0x22: "PAGE DOWN",
    0x23: "END", 0x24: "HOME", 0x25: "LEFT", 0x26: "UP", 0x27: "RIGHT", 0x28: "DOWN",
    0x2C: "PRINT SCREEN", 0x2D: "INSERT", 0x2E: "DELETE",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4", 0x35: "5",
    0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E", 0x46: "F",
    0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J", 0x4B: "K", 0x4C: "L",
    0x4D: "M", 0x4E: "N", 0x4F: "O", 0x50: "P", 0x51: "Q", 0x52: "R",
    0x53: "S", 0x54: "T", 0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X",
    0x59: "Y", 0x5A: "Z",
    0x60: "NUM 0", 0x61: "NUM 1", 0x62: "NUM 2", 0x63: "NUM 3", 0x64: "NUM 4",
    0x65: "NUM 5", 0x66: "NUM 6", 0x67: "NUM 7", 0x68: "NUM 8", 0x69: "NUM 9",
    0x6A: "NUM *", 0x6B: "NUM +", 0x6D: "NUM -", 0x6E: "NUM .", 0x6F: "NUM /",
    0x90: "NUM LOCK", 0x91: "SCROLL LOCK",
    0xBA: "SEMICOLON", 0xBB: "EQUALS", 0xBC: "COMMA", 0xBD: "MINUS",
    0xBE: "PERIOD", 0xBF: "SLASH", 0xC0: "BACKQUOTE",
    0xDB: "LEFT BRACKET", 0xDC: "BACKSLASH", 0xDD: "RIGHT BRACKET", 0xDE: "QUOTE",
}
for _i in range(24):
    VK_NAMES[0x70 + _i] = f"F{_i + 1}"
SCAN_VKS = sorted(set(VK_NAMES) | set(MOUSE_VKS) | set(VK_MODIFIERS))

# XInput
XINPUT_GAMEPAD = {
    0x0100: "GP UP", 0x0200: "GP DOWN", 0x0400: "GP LEFT", 0x0800: "GP RIGHT",
    0x0010: "GP START", 0x0020: "GP BACK", 0x0040: "GP L3", 0x0080: "GP R3",
    0x1000: "GP LB", 0x2000: "GP RB",
    0x4000: "GP A", 0x8000: "GP B", 0x100: "GP X", 0x200: "GP Y",
}
TRIGGERS = {"GP LT": 0, "GP RT": 1}

if _xinput is not None:
    class _XINPUT_STATE(ctypes.Structure):
        _fields_ = [("dwPacketNumber", wt.DWORD),
                    ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                    ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short),
                    ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                    ("wButtons", wt.WORD)]
    _xinput.XInputGetState.argtypes = [wt.DWORD, ctypes.POINTER(_XINPUT_STATE)]
    _xinput.XInputGetState.restype = wt.DWORD


def key_down(vk: int) -> bool:
    return bool(GetAsyncKeyState(vk) & 0x8000)


def compose_key(name: str, held: set[str]) -> str:
    mods = sorted(held - {name})
    return " + ".join(mods + [name]) if mods else name


class GlobalInput:
    """Passive hotkey polling. Callbacks run on the Tk main thread via `post`."""

    POLL_HZ = 60

    def __init__(self, post) -> None:
        self._post = post          # callable(callable) → run on UI thread
        self.on_event = None       # fn(key_string, "DOWN"|"UP")
        self.on_capture = None     # fn(key_string) — one-shot keybind capture
        self._capturing = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._down: set[str] = set()
        self._pad_down: set[str] = set()
        self._pad_poll_i = 0

    # lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="sightware-crosshair-input",
                                            daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def begin_capture(self) -> None:
        self._capturing = True

    def cancel_capture(self) -> None:
        self._capturing = False

    # polling loop ---------------------------------------------------------

    def _loop(self) -> None:
        interval = 1.0 / self.POLL_HZ
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass
            self._stop.wait(interval)

    def _tick(self) -> None:
        now_down: set[str] = set()

        for vk in SCAN_VKS:
            if key_down(vk):
                name = MOUSE_VKS.get(vk) or VK_MODIFIERS.get(vk) or VK_NAMES.get(vk)
                if name:
                    now_down.add(name)

        if self._capturing:
            # capture on release of a non-modifier key (like the original app)
            released = self._down - now_down
            for name in sorted(released):
                if name not in VK_MODIFIERS:
                    self._down.clear()
                    self._down |= now_down
                    cb = self.on_capture
                    if cb:
                        self._post(lambda n=compose_key(name, self._held_at_release(now_down, name)): cb(n))
                    self._capturing = False
                    return
        else:
            for name in now_down - self._down:
                self._emit(compose_key(name, now_down), "DOWN")
            for name in self._down - now_down:
                self._emit(compose_key(name, self._down & now_down | {name}), "UP")

        self._down = now_down
        self._tick_gamepad()

    def _held_at_release(self, now_down: set[str], name: str) -> set[str]:
        return now_down - {name}

    def _emit(self, key: str, state: str) -> None:
        cb = self.on_event
        if cb and key.strip():
            self._post(lambda k=key, s=state: cb(k, s))

    # gamepad (XInput, own controller only) ---------------------------------

    def _tick_gamepad(self) -> None:
        if _xinput is None:
            return
        self._pad_poll_i += 1
        if self._pad_poll_i % 2:      # ~30 Hz is plenty for buttons
            return
        state = _XINPUT_STATE()
        if _xinput.XInputGetState(0, ctypes.byref(state)) != 0:
            if self._pad_down:
                self._pad_down.clear()
            return
        now: set[str] = set()
        w = state.wButtons
        for mask, name in XINPUT_GAMEPAD.items():
            if w & mask:
                now.add(name)
        for name, idx in TRIGGERS.items():
            v = state.bLeftTrigger if idx == 0 else state.bRightTrigger
            if v > 64:
                now.add(name)
        if self.on_event or self._capturing:
            for name in now - self._pad_down:
                if self._capturing:
                    self._capturing = False
                    cb = self.on_capture
                    if cb:
                        self._post(lambda n=name: cb(n))
                else:
                    self._emit(name, "DOWN")
            for name in self._pad_down - now:
                self._emit(name, "UP")
        self._pad_down = now


# ── foreground window matching (no process handles, ever) ──────

def _window_title(hwnd) -> str:
    n = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def foreground_name() -> str:
    """Cached window title of the foreground window (no process access)."""
    hwnd = _user32.GetForegroundWindow()
    return _window_title(hwnd) if hwnd else ""


def foreground_matches(names: set[str]) -> bool:
    """True when the foreground window title matches one of the whitelist
    names. Reads only cached window properties — never opens a process."""
    title = foreground_name()
    if not title:
        return False
    t = title.casefold()
    return any(n.casefold() in t for n in names)
