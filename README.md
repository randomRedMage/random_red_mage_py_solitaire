Solitaire Suite (Pygame)

Overview
- Simple Pygame-based solitaire suite including Klondike, FreeCell, and Pyramid.
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

- FreeCell:
  - Drag single cards or valid descending, alternating sequences between tableau columns
  - Place one card per free cell (top-left)
  - Build foundations by suit from Ace upward (top-right)
  - `N`: New deal
  - `R`: Restart current deal
  - `U`: Undo last move
  - `A`: Auto-move available cards to foundations

- Pyramid:
  - Click the stock to flip to waste
  - Remove any exposed King, or any two exposed cards summing to 13
  - Limited stock resets based on options

Settings
- Use the in‑game Settings screen (from the main menu) to choose:
  - Card size: Small | Medium | Large
  - Card back: Blue/Grey/Red + variant
- Choices are saved to disk and applied at runtime:
  - Windows: `%APPDATA%/RandomRedMageSolitaire/settings.json`
  - macOS/Linux: `~/.random_red_mage_solitaire/settings.json`
- Rendering notes:
  - PNG image cards are used by default if available and are scaled to the selected size.
  - Falls back to vector‑drawn cards when images are unavailable.

Project Layout
- `src/solitaire/__main__.py`: entry point
- `src/solitaire/scenes/menu.py`: main menu
- `src/solitaire/modes/klondike.py`: Klondike options and game scenes
- `src/solitaire/modes/freecell.py`: FreeCell options and game scenes
- `src/solitaire/modes/pyramid.py`: Pyramid options and game scenes
- `src/solitaire/ui.py`: shared UI widgets (toolbar, buttons)
 - `packaging/pyinstaller/solitaire.spec`: PyInstaller build spec
 - `scripts/package_windows_pyinstaller.ps1`: Windows packaging helper
 - `scripts/package_macos_pyinstaller.sh`: macOS packaging helper

Notes
- Unicode cleanup: suit symbols now render as standard `♠ ♥ ♦ ♣`. If your system font misses them, image cards are used by default.
- Assets include card PNGs and a font license; see `src/solitaire/assets/` for details.
 - Hover Peek: in Klondike and FreeCell, hovering a partially covered, face‑up card reveals it in place after ~2 seconds so suits/ranks are readable. Move/scroll/click to cancel.

Contributing
- Dev setup:
  - Python 3.11+, `python -m pip install -e .` in the repo root
  - Run with `python -m solitaire` (ensure `PYTHONPATH` includes `src` if not installed)
- Code style:
  - Keep changes small and focused; match existing patterns and naming
  - Prefer adding a new mode under `src/solitaire/modes/<name>.py` with:
    - `<Name>OptionsScene` and `<Name>GameScene`
    - Toolbar via `solitaire.ui.make_toolbar`
    - Use shared primitives from `solitaire.common` (`Card`, `Pile`, `UndoManager`)
  - UI should respect window resizing and current card size from settings
- Manual QA checklist:
  - Resize window; verify layout recomputes
  - Start each mode; basic play loop works; Undo/Restart/New behave
  - Settings changes (size/back) persist and take effect without restart
  - Image cards load; fallback drawing looks acceptable

Known Issues / Future Work
- FreeCell: scrollbar is wheel/trackpad only; knob is not draggable yet
- FreeCell: cannot move cards back out of foundations (some variants allow this)
- Klondike/FreeCell: peek delay is fixed at ~2s; consider a settings toggle for delay/disable
- Asset loading does per‑size scaling on first use; initial draw may incur a brief cost
- Pyramid intentionally has no peek overlay (not needed for its mechanics)

Packaging
- PyInstaller (recommended for quick, cross‑platform bundles):
  - Windows (PowerShell): `./scripts/package_windows_pyinstaller.ps1`
  - macOS (Terminal): `bash ./scripts/package_macos_pyinstaller.sh`
  - Outputs to `dist/SolitaireSuite` (onedir). One‑file builds are supported by toggling the script flag but start slower.
- Notes:
  - Packaging scripts run `python -m pytest` before building and will abort if any test fails.
  - Test modules are excluded from the PyInstaller bundle to keep the distributable lean.
  - Assets (`src/solitaire/assets`) are bundled via the spec. If you add new files, they will be included automatically.
  - Pygame DLLs/frameworks are handled by PyInstaller hooks; no extra steps usually needed.
  - To set a custom icon, edit `packaging/pyinstaller/solitaire.spec` and set `icon` to a `.ico` (Windows) or `.icns` (macOS) path.
