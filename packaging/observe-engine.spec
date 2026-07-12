# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone Observe engine (variant C).

Freezes the JSON-RPC daemon + the whole ``framework`` package (including the
codegen ``.j2`` templates, collected as data) into one self-contained binary the
JetBrains plugin launches — so the end user needs no Python installed.

Build (from anywhere):  pyinstaller packaging/observe-engine.spec
Output:                 dist/observe-engine   (per the OS/arch it's built on)
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH is injected by PyInstaller = this file's directory; the repo root
# (where ``framework`` lives) is its parent. Using it keeps the build runnable
# regardless of the current working directory.
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is injected)

datas = collect_data_files("framework")  # includes framework/codegen/templates/**/*.j2
hiddenimports = collect_submodules("framework")

a = Analysis(
    [os.path.join(SPECPATH, "engine_entry.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="observe-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
