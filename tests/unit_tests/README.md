Unit Tests

This directory contains automated tests for the Solitaire app. They validate end‑to‑end scene flow (Title → Menu → Game options modal → Game → back) and basic invariants per game mode without rendering a real window.

What the tests cover
- App boot and main loop integration via `solitaire.__main__`
- Title and main menu transitions
- Game option modals driven by the main menu controllers for each mode
- Starting a new game from options and returning to the menu
- Light per‑mode assertions (e.g., pile counts, flags, basic layout defaults)

How they run headless
- Pygame runs in dummy mode via `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` set by the tests
- Fonts are stubbed with a simple dummy font implementation
- The display surface is a plain off‑screen `pygame.Surface`

Prerequisites
- Python 3.11+
- Project dependencies installed (e.g., `pygame>=2.6`). From the repo root:
  - `python -m venv .venv && source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)
  - `pip install -e .[test]` if you maintain an extra, or just `pip install -e . pytest`

Run the tests
- All tests: `pytest`
- Only unit tests: `pytest tests/unit_tests`
- Single test file: `pytest tests/unit_tests/test_app_flow.py`
- Verbose output: `pytest -q` or `pytest -vv`

Notes
- The app‑flow test parametrizes across all supported games using the controller registry in `solitaire.scenes.menu_options`.
- If you add a new game or adjust controller behaviour, update the mode entry in `tests/unit_tests/test_app_flow.py` accordingly.

