# Contributing to Sightware

Thanks for wanting to help. Sightware is a single-user, local-first desktop
app — no server, no web dashboard — so contributions are mostly code,
bug reports, and feedback. This doc gets you set up in five minutes.

## Project layout

```
run.py            launcher (python run.py; pythonw run.py for no console)
gui/              tkinter UI — app.py, theme.py, widgets.py, tabs/, dialogs.py
backend/          everything non-UI: Riot client session, live match state,
                  settings, crosshair engine, display/ChromaDesk layer
tests/            smoke tests (smoke_gui, smoke_core, smoke_crosshair, smoke_display)
tools/            one-off utilities
```

**House rule:** cross-module helpers go in `gui/widgets.py` / `gui/theme.py`,
never in individual tab files. Tab files import from the shared modules.
This exists because a helper defined in one tab silently breaks every other
importer once it's used under `pythonw` (no console, errors are invisible).

## Dev setup

1. Python 3.10+ (tkinter included — it ships with Python on Windows).
2. `pip install -r requirements.txt`
3. Run it: `python run.py` (use `pythonw run.py` to test the no-console path —
   do this at least once before submitting UI changes; console-only testing
   hides real errors).

## Before you open a PR

- Every file you touched compiles: `python -m py_compile <file>`
- The relevant smoke tests pass:
  - `python -I tests/smoke_gui.py` (UI changes)
  - `python -I tests/smoke_core.py` (backend changes)
  - `python -I tests/smoke_crosshair.py` (crosshair/overlay changes)
  - `python -I tests/smoke_display.py` (display/ChromaDesk changes)
- If you added a feature, add or extend a smoke test for it.
- Keep PRs focused. One bug or one feature per PR reads much better.

## Style notes

- Match the surrounding code — the codebase is plain, direct Python with
  sparse comments. Don't add comment density that isn't already there.
- No new runtime dependencies unless the feature genuinely needs one;
  the dependency list is deliberately short and pinned.
- UI values/colors go through `theme.py`, not hardcoded hex in tabs.
- Anything that touches the Riot client session must stay read-only and
  local — see [SECURITY.md](SECURITY.md) for the boundaries.

## Reporting bugs

Use the bug report template. Screenshots help a lot; log output (if any) and
your Windows/Python versions are required. If the bug involves the live
board or Encounters, note whether you were in a live game, in a match
detail dialog, etc.

## Feature requests

Open an issue with the feature template first for anything non-trivial —
especially if it would add a dependency, touch the overlay's click-through
behavior, or change the layout system.
