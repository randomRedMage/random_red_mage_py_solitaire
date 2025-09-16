param(
  [string]$Mode = "onedir"  # or 'onefile'
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  Write-Host "Installing PyInstaller..."
  python -m pip install pyinstaller
}

$spec = Join-Path $PSScriptRoot "..\packaging\pyinstaller\solitaire.spec"
Write-Host "Building using spec: $spec"


Write-Host "Running test suite..."
python -m pytest
if ($LASTEXITCODE -ne 0) {
  Write-Error "Tests failed. Packaging aborted."
  exit $LASTEXITCODE
}
Write-Host "Tests passed. Continuing with packaging."

if ($Mode -eq "onefile") {
  # Onefile tends to be slower to start for Pygame; supported if desired
  pyinstaller --noconfirm --clean --onefile --windowed --name SolitaireSuite `
    --exclude-module tests `
    --exclude-module pytest `
    --add-data "src/solitaire/assets;solitaire/assets" `
    src/solitaire/__main__.py
} else {
  pyinstaller --noconfirm --clean $spec
}

Write-Host "Build complete. Output under 'dist/SolitaireSuite'"

