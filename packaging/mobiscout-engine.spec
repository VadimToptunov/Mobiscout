# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone Mobiscout engine (variant C).

Freezes the JSON-RPC daemon + the whole ``framework`` package (including the
codegen ``.j2`` templates, collected as data) into one self-contained binary the
JetBrains plugin launches — so the end user needs no Python installed.

Build (from anywhere):  pyinstaller packaging/mobiscout-engine.spec
Output:                 dist/mobiscout-engine   (per the OS/arch it's built on)
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# SPECPATH is injected by PyInstaller = this file's directory; the repo root
# (where ``framework`` lives) is its parent. Using it keeps the build runnable
# regardless of the current working directory.
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (SPECPATH is injected)

datas = collect_data_files("framework")  # includes framework/codegen/templates/**/*.j2

# The Appium Python client reads its OWN version via importlib.metadata at import time
# (appium/version.py: version = _metadata_version('Appium-Python-Client')). A frozen binary
# carries no .dist-info by default, so `import appium` — every iOS / Appium-driver crawl —
# raised "No package metadata was found for Appium-Python-Client". Bundle the metadata;
# recursive=True also grabs the dependency metadata the stack (selenium, …) may read.
for _pkg in ("Appium-Python-Client", "selenium"):
    try:
        datas += copy_metadata(_pkg, recursive=True)
    except Exception:
        pass  # a source build without the client installed still freezes

hiddenimports = collect_submodules("framework")

# The compiled Rust accelerator. The release workflow installs the mobiscout_core wheel
# before freezing, so it must be collected into the binary — PyInstaller won't pick up a
# C-extension by name unless it's a hidden import, and its .so/.pyd needs collecting too.
# Guarded so a plain source build (no Rust wheel installed) still freezes; the release
# build's smoke test then asserts the frozen binary actually reports the "rust" backend.
binaries = []
try:
    import mobiscout_core  # noqa: F401

    from PyInstaller.utils.hooks import collect_dynamic_libs

    hiddenimports += ["mobiscout_core"]
    binaries += collect_dynamic_libs("mobiscout_core")
except ImportError:
    pass

a = Analysis(
    [os.path.join(SPECPATH, "engine_entry.py")],
    pathex=[REPO_ROOT],
    binaries=binaries,
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
    name="mobiscout-engine",
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
