# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['D:\\# Dev Test\\BUSCore-Test\\TGC-BUS-Core-main\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('core\\ui', 'core\\ui'), ('Flat-Dark.png', '.'), ('Glow-Hero.png', '.')],
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
    a.binaries,
    a.datas,
    [],
    name='BUS-Core',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='D:\\# Dev Test\\BUSCore-Test\\TGC-BUS-Core-main\\scripts\\_win_version_info.txt',
)
