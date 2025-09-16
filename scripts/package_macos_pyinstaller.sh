#!/usr/bin/env bash
set -euo pipefail

MODE="onedir"  # change to onefile if desired (slower startup)

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "Installing PyInstaller..."
  python3 -m pip install --user pyinstaller
  export PATH="$HOME/Library/Python/$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')/bin:$PATH"
fi

SPEC_DIR="$(cd "$(dirname "$0")/.." && pwd)/packaging/pyinstaller"
SPEC_FILE="$SPEC_DIR/solitaire.spec"

echo "Running test suite..."
if ! python3 -m pytest; then
  echo "Tests failed. Packaging aborted." >&2
  exit 1
fi
echo "Tests passed. Continuing with packaging."

echo "Building using spec: $SPEC_FILE"
if [[ "$MODE" == "onefile" ]]; then
  pyinstaller --noconfirm --clean --onefile --windowed \
    --name SolitaireSuite \
    --exclude-module tests \
    --exclude-module pytest \
    --add-data "src/solitaire/assets:solitaire/assets" \
    src/solitaire/__main__.py
else
  pyinstaller --noconfirm --clean "$SPEC_FILE"
fi

echo "Build complete. See dist/SolitaireSuite. On macOS, you can bundle into a .app via --windowed."

