Manual Test Launchers

This folder contains developer-only scripts to quickly launch specific game modes
and scenarios for manual verification (e.g., edge panning while dragging).

Usage

- Run the interactive launcher:
  - Python: `python tests/manual/run_manual.py`

What it does

- Prompts for a game mode and options, then starts the app directly in that scene.
- Optionally reshapes piles to create a very tall/wide layout to force scrollbars,
  making it easy to test edge panning while dragging.
- These options are applied via environment variables and are invisible to end users.

Environment variables (applied to the launched process)

- `SOLI_DEBUG_SCENE`: klondike | freecell | yukon | gate | bigben | beleaguered
- `SOLI_DEBUG_TALL`: 1/0 — force a tall (or wide) layout for edge-pan tests, where applicable
- `SOLI_CARD_SIZE`: Small | Medium | Large

