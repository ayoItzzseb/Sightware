<div align="center">

# Valtix

**Live VALORANT scoreboard, crosshair overlay, and display workspace —
one native Windows app. No web dashboard, no browser, no server. Just Python.**

Live Board · Performance · Encounters · Sessions · Collection ·
**Crosshair Overlay** · **Display (ChromaDesk)**

</div>

---

Valtix is a ground-up native tkinter rebuild of the old Flask + web dashboard
*plus* two built-in power tools:

- **Crosshair Overlay** — a fully featured crosshair editor and a
  click-through always-on-top overlay for borderless-windowed games.
- **Display workspace** — ChromaDesk's monitor controls: resolution modes,
  NVIDIA Digital Vibrance, desktop saturation, and display profiles.

Everything runs locally on your PC. Valtix talks only to your own Riot client
session (the same local API the game UI uses) — and the overlay/display tools
never touch game processes at all.

---

## 🚀 Install (Windows 10 / 11)

### What you need

| Requirement | Notes |
|---|---|
| **Windows 10 or 11** (64-bit) | Display & overlay features are Windows-only |
| **Python 3.12+** | [python.org](https://www.python.org/downloads/) — tick **"Add python.exe to PATH"** during install |
| **VALORANT** (optional) | Without it, Valtix runs on clearly-labelled demo data |
| **NVIDIA GPU + driver** (optional) | Only needed for Digital Vibrance; everything else works on any GPU |

### Steps

1. **Download or clone this repository** to any folder, e.g. `C:\Tools\Valtix`.

2. **Double-click `install.bat`.** It checks your Python version, installs
   the pinned packages (`requests`, `python-dotenv`, `tzdata`, `rich`,
   `pillow` — five, that is it), verifies the install, and offers to launch.

3. **Double-click `start.bat`** to run Valtix any time
   (or `python run.py --console` in a terminal for debug logging).

4. *(Optional)* ⚙ **Settings** → *Start with Windows* adds Valtix to your
   Startup folder.

> **Prefer a single `.exe`?** Run `build.bat` — it produces
> `dist\Valtix\Valtix.exe` with PyInstaller (no Python needed on the target
> PC). Note: on PCs with **Smart App Control** enabled, unsigned freshly
> built executables can be blocked; run from source (steps 2–3), or
> distribute signed / through the Microsoft Store.

### First run

- With VALORANT open, the Live Board goes **LIVE · LOCAL CLIENT** and shows
  your real lobby. Without it, Valtix runs on demo data so you can explore
  everything.
- Data (history, sessions, crosshair library, display profiles) is created on
  first run under `backend\data\` — and that folder is yours: back it up,
  copy it, share presets with friends.

---

## ✨ Features

| Tab | What it does |
|---|---|
| **Live Board** | Full scoreboard: ranks, RR, peak rank, account level, party color chips, per-map win probability, agent portraits, smurf radar tags, K/D · HS% · WR recent form. Agent Select pick-advisor banner and the optional ⚡ INSTA-LOCK button (off by default, policy acknowledgement required, one press = one select + lock). The FINAL match scoreboard card fills in the moment Riot publishes the match, fully sortable. |
| **Performance** | RR history chart with hover tooltips, win-rate / net-RR / personal-best cards, next-rank progress bar, per-agent & per-map splits, weekday/daypart schedule, promotion & demotion log, last 60 matches (click → full match report with round timeline), per-match notes/tags/bookmarks, play-calendar heatmap, multi-account switcher. |
| **Encounters** | Local smurf radar: everyone you played with or against (2+ games), W–L with/against, top agent, K/D & HS% alongside, rank/peak, last seen. |
| **Sessions** | Session tracker with goals (+RR, reach rank, N matches, stop-loss), live goal progress, archive with outcomes. |
| **Collection** | Skin collection value (VP + USD approx), wallet, rarity breakdown, top skins, recent acquisitions — read locally from your client. |
| **Crosshair** | Full crosshair overlay: cross / circle / dot editor with per-line toggles, outline and alpha, a 32×32 pixel-art editor, PNG image crosshairs, preset library with one-click **Simple Sight import**, quickload hotkeys (F1–F4), hide/show hotkey (F10), aim-down-sights mode (hold MOUSE RIGHT to hide the crosshair or switch to a second one), optional gamepad bindings, per-app visibility whitelist. Live preview mirrors the overlay exactly; rendering is antialiased. |
| **Display** | ChromaDesk integrated: per-monitor resolution modes (favorites + Windows' own 15-second apply-or-revert confirmation), NVIDIA Digital Vibrance, whole-desktop saturation (0–300 % via the Magnification API), manual display profiles, restore-on-exit. |

Plus: ⚙ Settings dialog with every switch, queue & match alerts with toasts
and sounds, dark title bar, window/tab memory, and a two-press **Quit Valtix**.

---

## 🎯 Crosshair overlay and anti-cheat (read this)

The overlay was designed **from the ground up to be as passive as possible**:

- **No hooks** — hotkeys are read with passive `GetAsyncKeyState` polling;
  nothing is installed into the input pipeline.
- **No process access** — Valtix never opens a handle to any game process,
  reads no memory, captures no frames.
- **A plain see-through window** — the overlay is a topmost layered window
  that only draws its own pixels; clicks pass straight through to your game.
- **Display tools** use Windows display APIs and the NVIDIA driver only.

That is the same category as common commercial crosshair overlays. Still, be
aware: **no third-party tool can be guaranteed with any anti-cheat**, and you
use it at your own discretion.

> **Borderless windowed required:** exclusive-fullscreen games own the whole
> display surface and hide *any* topmost overlay. Run VALORANT in
> **borderless windowed** mode to see the crosshair.

---

## 🔒 Privacy

Valtix is 100 % local. Dashboard, settings, history, statistics, the crosshair
library and display profiles live on this PC. Riot communication is only your
own client session — the same local API the game UI uses. No telemetry, no
accounts, no cloud.

---

## 🧪 Tests

```text
python -I tests\smoke_gui.py         # full app: every tab builds, boards flow
python -I tests\smoke_crosshair.py   # overlay engine, click-through, editor
python -I tests\smoke_display.py     # display engine, profiles, revert flow
```

All three print `ALL CHECKS PASSED` on a healthy install.

---

## 🏗️ Architecture

```
run.py                  entry point (puts backend/ on sys.path)
backend/                flat domain modules (riot_client, live_match, history,
                        encounter_log, session_tracker, inventory, ...)
  crosshair_*           overlay engine: store / render / input / overlay
  display_engine.py     ChromaDesk: display modes, NVAPI, magnification, profiles
gui/                    tkinter app: theme, widgets, tabs/, dialogs
tests/                  smoke tests (no network needed)
install.bat / start.bat / build.bat
Valtix.spec             PyInstaller spec for build.bat
```

Tab UIs are plain `tk.Frame`s registered in `gui/app.py`; heavy work runs on
worker threads and reaches the UI through a thread-safe queue.

---

## 📜 License and disclaimer

Released under the **GPL-3.0** license (see `LICENSE`). Includes the
ChromaDesk display engine by the same author.

VALORANT is a trademark of Riot Games, Inc. Valtix is an independent local
utility, not affiliated with or endorsed by Riot Games. Use of in-game
overlays is at your own discretion.
