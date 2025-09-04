Solitaire Suite (Pygame)

Overview
- Simple Pygame-based solitaire suite including Klondike and Pyramid.
- Uses built-in vector drawing with optional image card assets bundled under `src/solitaire/assets`.

Requirements
- Python 3.11+
- pip
- Windows, macOS, or Linux with a display (Pygame)

Install and Run
- Quick run without install:
  - PowerShell (Windows):
    - `cd` to the repo root
    - `setx PYTHONPATH "%CD%\src"` then restart the shell; or for the current session:
      - `$env:PYTHONPATH = (Join-Path (Get-Location) 'src')`
    - Run: `python -m solitaire`
  - Bash (macOS/Linux):
    - `export PYTHONPATH=$PWD/src`
    - `python -m solitaire`

- Optional editable install (preferred):
  - `python -m pip install -e .`
  - `python -m solitaire`

Controls
- Global:
  - `Esc`: Back to menu or quit from menu

- Klondike:
  - Click stock to draw (draw 1 or 3 based on options)
  - Drag cards/stacks to valid targets
  - `N`: New deal
  - `R`: Restart current deal
  - `U`: Undo last move
  - `A`: Auto-finish when available

- Pyramid:
  - Click the stock to flip to waste
  - Remove any exposed King, or any two exposed cards summing to 13
  - Limited stock resets based on options

Settings
- Card assets and style are configured in `src/solitaire/common.py`:
  - `USE_IMAGE_CARDS`: use PNG assets if available; falls back to drawn cards
  - `BACK_COLOR` and `BACK_VARIANT`: choose the card back style
  - `IMAGE_CARDS_DIR`: path to preferred card face size (`PNG/Medium` by default)

Project Layout
- `src/solitaire/__main__.py`: entry point
- `src/solitaire/scenes/menu.py`: main menu
- `src/solitaire/modes/klondike.py`: Klondike options and game scenes
- `src/solitaire/modes/pyramid.py`: Pyramid options and game scenes
- `src/solitaire/ui.py`: shared UI widgets (toolbar, buttons)

Notes
- Unicode cleanup: suit symbols now render as standard `♠ ♥ ♦ ♣`. If your system font misses them, image cards are used by default.
- Assets include card PNGs and a font license; see `src/solitaire/assets/` for details.

