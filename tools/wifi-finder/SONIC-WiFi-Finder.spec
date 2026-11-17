# -*- mode: python ; coding: utf-8 -*-
"""Native PyInstaller bundle; run scripts/build_native.py on the target OS."""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
APP_NAME = "SONIC WiFi Finder" if IS_MAC else "SONIC-WiFi-Finder"
ICON = ROOT / "assets" / ("app-icon.icns" if IS_MAC else "app-icon.ico")
DATAS = [(str(ROOT / "assets"), "assets"), (str(ROOT / "licenses"), "licenses")]
if (ROOT / "THIRD_PARTY_NOTICES.md").exists():
    DATAS.append((str(ROOT / "THIRD_PARTY_NOTICES.md"), "."))

a = Analysis(
    [str(ROOT / "wifi_finder.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
COMMON = dict(
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=os.environ.get("SONIC_CODESIGN_IDENTITY") or None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)
if IS_MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **COMMON)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)
    app = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        icon=str(ICON) if ICON.exists() else None,
        bundle_identifier="com.sonic.wififinder",
        info_plist={
            "CFBundleName": "SONIC WiFi Finder",
            "CFBundleDisplayName": "SONIC WiFi Finder",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "SONIC",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **COMMON)
