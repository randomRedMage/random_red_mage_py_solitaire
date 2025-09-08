# PyInstaller spec for Solitaire Suite (Windows/macOS)
# Produces a windowed, onedir app with bundled assets.

import os, sys
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree

# Resolve repo root relative to this spec file; fall back to sys.argv[0] when __file__ is not set
try:
    _spec_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _spec_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
here = os.path.abspath(os.path.join(_spec_dir, '..', '..'))
entry = os.path.join(here, 'src', 'solitaire', '__main__.py')

# Bundle asset tree under the same relative path inside the app
assets_dir = os.path.join(here, 'src', 'solitaire', 'assets')
assets_tree = []
if os.path.isdir(assets_dir):
    # Prefix to keep package-like path for runtime lookups
    assets_tree = [Tree(assets_dir, prefix=os.path.join('solitaire', 'assets'))]

# Pygame can use hidden imports depending on platform; collect just in case
hidden = collect_submodules('pygame')

a = Analysis(
    [entry],
    pathex=[here],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    *assets_tree,
    name='SolitaireSuite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # windowed
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # set to a .ico/.icns path if you add one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *assets_tree,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SolitaireSuite'
)
