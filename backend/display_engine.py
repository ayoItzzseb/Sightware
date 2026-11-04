"""Display engine — ChromaDesk's display controls integrated into Valtix.

Lifted from the ChromaDesk prototype (Desktop/ChromaDeskPrototype): Windows
display-mode enumeration/switching, NVIDIA Digital Vibrance (NVAPI), and
whole-desktop saturation (Magnification API), plus the display-profile store.

Safety boundary unchanged from ChromaDesk: Windows display APIs and the NVIDIA
driver only — no game-process enumeration, hooks, injection, memory access, or
input automation.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import threading
from ctypes import wintypes
from pathlib import Path

# ── Windows display modes ──────────────────────────────────────

class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmOrientation", ctypes.c_short),
        ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short),
        ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short),
        ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


DM_BITSPERPEL = 0x00040000
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00200000
CDS_TEST = 0x00000002
CDS_FULLSCREEN = 0x00000004
DISP_CHANGE_SUCCESSFUL = 0
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class WindowsDisplay:
    """Windows display modes, enumerated and applied per attached display."""
    def __init__(self):
        if platform.system() != "Windows":
            raise OSError("Display controls are available on Windows only.")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
        self.user32.EnumDisplayDevicesW.restype = wintypes.BOOL
        self.user32.EnumDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW), wintypes.DWORD]
        self.user32.EnumDisplaySettingsExW.restype = wintypes.BOOL
        self.user32.ChangeDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(DEVMODEW), wintypes.HWND, wintypes.DWORD, wintypes.LPVOID]
        self.user32.ChangeDisplaySettingsExW.restype = ctypes.c_long
        self.devices = []
        self.device = None
        self.device_info = None
        self.modes = []
        self.current = None
        self.current_bpp = 32
        self.original_modes = {}
        self.original_bpp = {}
        self.changed_modes = set()
        self.refresh()

    @staticmethod
    def _new_mode():
        mode = DEVMODEW()
        mode.dmSize = ctypes.sizeof(DEVMODEW)
        return mode

    def _read_mode(self, device_name, index):
        mode = self._new_mode()
        if not self.user32.EnumDisplaySettingsExW(device_name, index, ctypes.byref(mode), 0):
            return None
        if not mode.dmPelsWidth or not mode.dmPelsHeight:
            return None
        return mode

    def _enumerate_devices(self):
        devices = []
        index = 0
        while True:
            adapter = DISPLAY_DEVICEW()
            adapter.cb = ctypes.sizeof(adapter)
            if not self.user32.EnumDisplayDevicesW(None, index, ctypes.byref(adapter), 0):
                break
            if adapter.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                monitor = DISPLAY_DEVICEW()
                monitor.cb = ctypes.sizeof(monitor)
                monitor_name = ""
                if self.user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(monitor), 0):
                    monitor_name = monitor.DeviceString.strip()
                devices.append({
                    "name": adapter.DeviceName.strip(),
                    "adapter": adapter.DeviceString.strip(),
                    "monitor": monitor_name or adapter.DeviceString.strip(),
                    "primary": bool(adapter.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
                })
            index += 1
        if not devices:
            raise OSError("Windows did not report any displays attached to the desktop.")
        return devices

    def refresh(self, selected_device=None):
        previous = selected_device or self.device
        devices = self._enumerate_devices()
        self.devices = devices
        for info in devices:
            name = info["name"]
            current = self._read_mode(name, ENUM_CURRENT_SETTINGS)
            if current is None:
                continue
            current_tuple = (int(current.dmPelsWidth), int(current.dmPelsHeight), int(current.dmDisplayFrequency or 0))
            info["current"] = current_tuple
            if name not in self.original_modes:
                self.original_modes[name] = current_tuple
                self.original_bpp[name] = int(current.dmBitsPerPel or 32)
        names = {item["name"] for item in devices}
        if previous not in names:
            primary = next((item for item in devices if item["primary"]), devices[0])
            previous = primary["name"]
        self.select_device(previous)

    def select_device(self, device_name):
        info = next((item for item in self.devices if item["name"] == device_name), None)
        if info is None:
            raise OSError("The selected display is no longer attached to the Windows desktop.")
        current = self._read_mode(device_name, ENUM_CURRENT_SETTINGS)
        if current is None:
            raise OSError(f"Windows could not read the current mode for {device_name}.")
        self.device = device_name
        self.device_info = info
        self.current = (int(current.dmPelsWidth), int(current.dmPelsHeight), int(current.dmDisplayFrequency or 0))
        self.current_bpp = int(current.dmBitsPerPel or 32)
        found = set()
        index = 0
        while True:
            mode = self._read_mode(device_name, index)
            if mode is None:
                break
            found.add((int(mode.dmPelsWidth), int(mode.dmPelsHeight), int(mode.dmDisplayFrequency or 0)))
            index += 1
        self.modes = sorted(found, key=lambda item: (item[0], item[1], item[2]))

    def set_mode(self, mode_tuple, test=False, device_name=None):
        target_device = device_name or self.device
        w, h, hz = mode_tuple
        mode = self._new_mode()
        mode.dmFields = DM_BITSPERPEL | DM_PELSWIDTH | DM_PELSHEIGHT
        mode.dmBitsPerPel = self.current_bpp if target_device == self.device else self.original_bpp.get(target_device, 32)
        mode.dmPelsWidth = w
        mode.dmPelsHeight = h
        if hz:
            # A reported 0 Hz means "Windows default"; leave the field unset so Windows keeps it.
            mode.dmFields |= DM_DISPLAYFREQUENCY
            mode.dmDisplayFrequency = int(hz)
        flags = CDS_TEST if test else CDS_FULLSCREEN
        result = int(self.user32.ChangeDisplaySettingsExW(target_device, ctypes.byref(mode), None, flags, None))
        if not test and result == DISP_CHANGE_SUCCESSFUL:
            if mode_tuple == self.original_modes.get(target_device):
                self.changed_modes.discard(target_device)
            else:
                self.changed_modes.add(target_device)
        return result


# ── NVIDIA Digital Vibrance (NVAPI) ────────────────────────────

class DVCInfo(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint), ("currentLevel", ctypes.c_uint),
                ("minLevel", ctypes.c_uint), ("maxLevel", ctypes.c_uint)]


class NvidiaDVC:
    """NVAPI Digital Vibrance wrapper with explicit GDI display-name mapping."""
    QUERY_IDS = {
        "initialize": 0x0150E828,
        "enum_display": 0x9ABDD40D,
        "associated_display": 0x35C29134,
        "get_dvc": 0x4085DE45,
        "set_dvc": 0x172409B4,
    }

    def __init__(self, device_name=None):
        if platform.system() != "Windows":
            raise OSError("NVIDIA driver controls require Windows.")
        for dll_name in ("nvapi64.dll", "nvapi.dll"):
            try:
                self.dll = ctypes.WinDLL(dll_name)
                break
            except OSError:
                continue
        else:
            raise OSError("NVIDIA NVAPI driver library was not found. Confirm that an NVIDIA GPU and current NVIDIA driver are installed.")
        query = self.dll.nvapi_QueryInterface
        query.argtypes = [ctypes.c_uint]
        query.restype = ctypes.c_void_p
        self.initialize = self._function(query, "initialize", ctypes.c_int, [])
        self.enum_display = self._function(query, "enum_display", ctypes.c_int, [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)])
        self.associated_display = self._function(query, "associated_display", ctypes.c_int, [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)])
        self.get_dvc = self._function(query, "get_dvc", ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(DVCInfo)])
        self.set_dvc = self._function(query, "set_dvc", ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint])
        self._status(self.initialize(), "initialize NVIDIA API")
        self.device_name = None
        self.display_handle = None
        self.original_levels = {}
        self.original_infos = {}
        self.modified = set()
        self.error = None
        if device_name:
            try:
                self.select_display(device_name)
            except Exception as exc:
                self.error = str(exc)

    @property
    def original(self):
        return self.original_infos.get(self.device_name)

    def _function(self, query, key, restype, argtypes):
        address = query(self.QUERY_IDS[key])
        if not address:
            raise OSError(f"The installed NVIDIA driver does not expose the required {key} control.")
        return ctypes.CFUNCTYPE(restype, *argtypes)(address)

    @staticmethod
    def _status(status, operation):
        if status != 0:
            raise OSError(f"NVIDIA driver could not {operation} (NVAPI status {status}).")

    def select_display(self, device_name):
        self.device_name = str(device_name)
        handle = ctypes.c_void_p()
        try:
            encoded_name = self.device_name.encode("ascii")
        except UnicodeEncodeError as exc:
            self.display_handle = None
            raise OSError("Windows returned an unsupported display identifier for NVIDIA mapping.") from exc
        status = int(self.associated_display(encoded_name, ctypes.byref(handle)))
        if status != 0 or not handle:
            self.display_handle = None
            raise OSError(f"No NVIDIA Digital Vibrance control is associated with {self.device_name} (NVAPI status {status}).")
        self.display_handle = handle
        info = self.read()
        if self.device_name not in self.original_levels:
            self.original_levels[self.device_name] = int(info.currentLevel)
            self.original_infos[self.device_name] = info
        self.error = None
        return info

    def read(self):
        if self.display_handle is None:
            raise OSError(self.error or f"No NVIDIA display handle is active for {self.device_name or 'the selected display'}.")
        info = DVCInfo()
        info.version = ctypes.sizeof(DVCInfo) | 0x10000
        self._status(self.get_dvc(self.display_handle, 0, ctypes.byref(info)), "read Digital Vibrance")
        return info

    def set(self, level):
        info = self.read()
        level = int(max(info.minLevel, min(info.maxLevel, int(level))))
        self._status(self.set_dvc(self.display_handle, 0, level), "set Digital Vibrance")
        self.modified.add(self.device_name)
        return level

    def restore_current(self):
        original = self.original_levels.get(self.device_name)
        if original is None:
            raise OSError("The original Digital Vibrance level for this display was not captured.")
        restored = self.set(original)
        self.modified.discard(self.device_name)
        return restored

    def restore(self):
        errors = []
        for device_name in list(self.modified):
            try:
                self.select_display(device_name)
                self.set(self.original_levels[device_name])
                self.modified.discard(device_name)
            except Exception as exc:
                errors.append(f"{device_name}: {exc}")
        if errors:
            raise OSError("Could not restore NVIDIA Digital Vibrance on all changed displays: " + "; ".join(errors))


# ── whole-desktop saturation (Magnification API) ───────────────

class MAGCOLOREFFECT(ctypes.Structure):
    _fields_ = [("transform", ctypes.c_float * 25)]


class MagnifierSaturation:
    """Whole-desktop saturation through the built-in Windows Magnification API."""
    IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 1.0)

    def __init__(self):
        if platform.system() != "Windows":
            raise OSError("The Windows full-desktop color filter is only available on Windows.")
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise OSError("The full-screen Windows Magnification API requires a 64-bit Python runtime on 64-bit Windows.")
        self.dll = ctypes.WinDLL("Magnification.dll", use_last_error=True)
        self.dll.MagInitialize.argtypes = []
        self.dll.MagInitialize.restype = wintypes.BOOL
        self.dll.MagGetFullscreenColorEffect.argtypes = [ctypes.POINTER(MAGCOLOREFFECT)]
        self.dll.MagGetFullscreenColorEffect.restype = wintypes.BOOL
        self.dll.MagSetFullscreenColorEffect.argtypes = [ctypes.POINTER(MAGCOLOREFFECT)]
        self.dll.MagSetFullscreenColorEffect.restype = wintypes.BOOL
        self.dll.MagUninitialize.argtypes = []
        self.dll.MagUninitialize.restype = wintypes.BOOL
        if not self.dll.MagInitialize():
            raise ctypes.WinError(ctypes.get_last_error(), "Windows Magnification API initialization failed")
        self.initialized = True
        self.active = False
        self.percent = 100
        self.warmth = 0
        self.applied_matrix = None
        self.original = MAGCOLOREFFECT()
        if not self.dll.MagGetFullscreenColorEffect(ctypes.byref(self.original)):
            # Do not uninitialize when the existing global effect is unknown;
            # Windows may clear it as part of Magnification API teardown.
            raise ctypes.WinError(ctypes.get_last_error(), "Could not read the existing Windows desktop color effect")
        self.has_existing_effect = not self._matches(self.original.transform, self.IDENTITY)

    @staticmethod
    def _matches(actual, expected):
        return all(abs(float(value) - float(target)) <= 0.00001 for value, target in zip(actual, expected))

    @staticmethod
    def _matrix(percent):
        saturation = max(0, min(300, int(percent))) / 100.0
        # MAGCOLOREFFECT uses Red, Blue, Green channels and GDI+'s row-vector
        # convention: rows are input channels, columns are output channels.
        luminance = (0.2126, 0.0722, 0.7152)
        matrix = []
        for row in range(3):
            matrix.extend(
                luminance[row] * (1.0 - saturation) + (saturation if row == col else 0.0)
                for col in range(3)
            )
            matrix.extend((0.0, 0.0))
        matrix.extend((0.0, 0.0, 0.0, 1.0, 0.0,
                       0.0, 0.0, 0.0, 0.0, 1.0))
        return tuple(matrix)

    def _set(self, values):
        effect = MAGCOLOREFFECT((ctypes.c_float * 25)(*values))
        if not self.dll.MagSetFullscreenColorEffect(ctypes.byref(effect)):
            raise ctypes.WinError(ctypes.get_last_error(), "Windows could not apply the full-desktop color filter")

    def set_percent(self, percent):
        if self.has_existing_effect:
            raise OSError("A non-neutral Windows desktop color effect is already active. Disable it and restart Valtix before applying saturation.")
        current = MAGCOLOREFFECT()
        if not self.dll.MagGetFullscreenColorEffect(ctypes.byref(current)):
            raise ctypes.WinError(ctypes.get_last_error(), "Could not verify the current desktop effect before updating saturation")
        expected = self.applied_matrix if self.active else self.original.transform
        if not self._matches(current.transform, expected):
            raise OSError("Another color tool changed the Windows desktop effect. Valtix stopped live updates and left that effect untouched.")
        percent = max(0, min(300, int(percent)))
        self.percent = percent
        matrix = self._combined()
        self._set(matrix)
        self.active = not self._is_identity(matrix)
        self.applied_matrix = matrix
        return percent

    @staticmethod
    def _is_identity(matrix):
        return MagnifierSaturation._matches(matrix, MagnifierSaturation.IDENTITY)

    def set_warmth(self, pct):
        """0 = neutral, 100 = warm (redder), -100..0 cool (bluer)."""
        self.warmth = max(-100, min(100, int(pct)))
        self.percent = self.percent or 100
        matrix = self._combined()
        self._set(matrix)
        self.active = not self._is_identity(matrix)
        self.applied_matrix = matrix
        return self.warmth

    def _combined(self):
        """Saturation and warmth matrices composed (row-vector convention)."""
        warm = self.warmth
        if not warm:
            return self._matrix(self.percent)
        t = warm / 100.0
        # MAGCOLOREFFECT channels are Red, Blue, Green (R-B-G) — warm raises
        # red, lowers blue, green nearly unchanged.
        warm_m = (1.0 + 0.15 * t, 0.0, 0.0, 0.0, 0.0,
                  0.0, 1.0 - 0.25 * t, 0.0, 0.0, 0.0,
                  0.0, 0.0, 1.0 + 0.03 * t, 0.0, 0.0,
                  0.0, 0.0, 0.0, 1.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 1.0)
        sat = self._matrix(self.percent)
        # row-vector compose: out = sat_row * warm_m (5x5, last row/col affine)
        out = []
        for r in range(5):
            for cIdx in range(5):
                acc = 0.0
                for k in range(5):
                    acc += sat[r * 5 + k] * warm_m[k * 5 + cIdx]
                out.append(acc)
        return tuple(out)

    def restore(self):
        if self.active:
            current = MAGCOLOREFFECT()
            if not self.dll.MagGetFullscreenColorEffect(ctypes.byref(current)):
                raise ctypes.WinError(ctypes.get_last_error(), "Could not verify the current desktop effect before restoring")
            if not self._matches(current.transform, self.applied_matrix):
                raise OSError("Another color tool changed the Windows desktop effect. Valtix left the current effect untouched.")
            self._set(self.original.transform)
            self.active = False
            self.percent = 100
            self.warmth = 0
            self.applied_matrix = None

    def shutdown(self):
        if not getattr(self, "initialized", False):
            return
        if self.active:
            self.restore()
        current = MAGCOLOREFFECT()
        if not self.dll.MagGetFullscreenColorEffect(ctypes.byref(current)):
            raise ctypes.WinError(ctypes.get_last_error(), "Could not verify the desktop color effect before cleanup")
        if self.has_existing_effect or not self._matches(current.transform, self.IDENTITY):
            # Keep the captured non-identity effect (or a later external effect);
            # MagUninitialize could clear that global color transform.
            self.initialized = False
            return
        if not self.dll.MagUninitialize():
            raise ctypes.WinError(ctypes.get_last_error(), "Windows Magnification API cleanup failed")
        self.initialized = False


def mode_label(mode):
    w, h, hz = mode
    return f"{w} × {h}   ·   {hz or 'Default'} Hz"


# Magnification is process-global: a second MagInitialize pair would let one
# owner's MagUninitialize tear down another's filter. Keep exactly one.
_SAT_SINGLETON = None
_SAT_ERROR: str | None = None


def get_saturation():
    """Process-wide MagnifierSaturation, or None with _SAT_ERROR set."""
    global _SAT_SINGLETON, _SAT_ERROR
    if _SAT_SINGLETON is None and _SAT_ERROR is None:
        try:
            _SAT_SINGLETON = MagnifierSaturation()
        except Exception as exc:
            _SAT_ERROR = str(exc)
    return _SAT_SINGLETON


def saturation_error() -> str | None:
    get_saturation()
    return _SAT_ERROR


# ── display profiles (Valtix data dir) ─────────────────────────

_DATA_DIR = (os.environ.get("VALTIX_DATA_DIR")
             or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
_PROFILES = os.path.join(_DATA_DIR, "display", "profiles.json")
_LOCK = threading.RLock()

# one-time adoption of profiles from the standalone ChromaDesk app
_CHROMADESK_PROFILES = os.path.join(os.environ.get("APPDATA", ""), "ChromaDesk", "profiles.json")


def profiles_path() -> str:
    return _PROFILES


def read_profiles() -> dict:
    with _LOCK:
        if not os.path.isfile(_PROFILES):
            try:
                if os.path.isfile(_CHROMADESK_PROFILES):
                    data = json.loads(Path(_CHROMADESK_PROFILES).read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        _write_profiles_raw(data)
                        return data
            except Exception:
                pass
            return {}
        try:
            data = json.loads(Path(_PROFILES).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _write_profiles_raw(profiles: dict) -> None:
    path = Path(_PROFILES)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    temp.replace(path)


def write_profiles(profiles: dict) -> None:
    with _LOCK:
        _write_profiles_raw(profiles)
