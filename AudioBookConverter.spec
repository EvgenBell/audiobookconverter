# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

# Resolve Windows ICU from System32 before unrelated tools on the build PATH.
if os.name == 'nt':
    os.environ['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32') + os.pathsep + os.environ['PATH']

a = Analysis(
    ['src\\app.py'],
    pathex=['src'],
    binaries=[('bin\\ffmpeg.exe', 'bin'), ('bin\\ffprobe.exe', 'bin')],
    datas=[('src\\i18n', 'i18n'), ('src\\resources\\*.svg', 'resources'), ('icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AudioBookConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AudioBookConverter',
)
