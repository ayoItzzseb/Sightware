<!-- One bug fix or one feature per PR. Link the issue if there is one. -->

## What does this PR do?

<!-- Short summary. "Fixes #123" / "Closes #123" if applicable. -->

## Type of change

- [ ] Bug fix (non-breaking, fixes something that was broken)
- [ ] New feature (non-breaking, adds functionality)
- [ ] Refactor (no behavior change)
- [ ] Docs / templates only

## Area(s) touched

<!-- e.g. Live Board, Encounters, crosshair overlay, backend/live_match.py, ... -->

## Testing

<!-- Tick what you actually ran. -->

- [ ] `python -m py_compile` on every file I touched
- [ ] `python -I tests/smoke_gui.py` passes (UI changes)
- [ ] `python -I tests/smoke_core.py` passes (backend changes)
- [ ] `python -I tests/smoke_crosshair.py` passes (crosshair changes)
- [ ] `python -I tests/smoke_display.py` passes (display changes)
- [ ] Ran the app under `pythonw run.py` at least once (UI changes)
- [ ] Added/extended a smoke test for new functionality

## House rules

- [ ] Cross-module helpers went into `gui/widgets.py` / `gui/theme.py` (not a tab file)
- [ ] No hardcoded colors outside `theme.py` (UI changes)
- [ ] No new runtime dependency without discussing it first
- [ ] Riot client interaction stays read-only and local
