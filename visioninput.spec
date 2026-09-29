# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for VisionInput.
Build with: pyinstaller visioninput.spec --distpath=dist
"""
import sys
from pathlib import Path
import os
try:
    import vgamepad
    _vgamepad_pkg = Path(vgamepad.__file__).parent
    _vgamepad_dlls = []
    _vgamepad_datas = []
    # include entire vgamepad/win tree as datas so frozen app can locate DLLs by path
    _vg_win = _vgamepad_pkg / 'win'
    if _vg_win.exists():
        for p in _vg_win.rglob('*'):
            if p.is_file():
                rel = p.relative_to(_vgamepad_pkg)
                dest = os.path.join('vgamepad', str(rel.parent))
                _vgamepad_datas.append((str(p), dest))
    for _arch in ("x64", "x86"):
        _p = _vgamepad_pkg / 'win' / 'vigem' / 'client' / _arch / 'ViGEmClient.dll'
        if _p.exists():
            _vgamepad_dlls.append((str(_p), os.path.join('vgamepad', 'win', 'vigem', 'client', _arch)))
except Exception:
    _vgamepad_dlls = []
    _vgamepad_datas = []

try:
    import mediapipe
    _mp_pkg = Path(mediapipe.__file__).parent
    _mediapipe_datas = []
    # Include all files from mediapipe package (preserve relative structure)
    for p in _mp_pkg.rglob('*'):
        if p.is_file():
            rel = p.relative_to(_mp_pkg)
            dest = os.path.join('mediapipe', str(rel.parent))
            _mediapipe_datas.append((str(p), dest))
except Exception:
    _mediapipe_datas = []

# Ensure gesture_map.json absolute path is included when present
_mapfile = Path(SPECPATH) / 'config' / 'gesture_map.json'
if _mapfile.exists():
    _gesture_map_data = [(str(_mapfile), 'config')]
else:
    _gesture_map_data = []

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=_vgamepad_dlls,
    datas=[
        ('src/config.py', 'src'),
        ('src/gesture_mapping.py', 'src'),
        ('src/vigem_output.py', 'src'),
        ('src/visualiser.py', 'src'),
        ('src/setup_camera.py', 'src'),
    ] + _gesture_map_data + _mediapipe_datas + _vgamepad_datas + [('src/_embedded_gesture_map.py', 'src')],
    hiddenimports=['cv2', 'mediapipe', 'numpy', 'asyncio', 'websockets',
                   'numpy._core._exceptions', 'numpy._core._multiarray_umath', 'numpy._core._multiarray'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['src/rth_vigem.py'],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VisionInput',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
