# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FishShopPOS.exe.

Built from packaging/.build-venv-pos (see packaging/scripts/build_windows.ps1),
which installs only apps/pos/requirements.txt + packaging/pyinstaller/
build-requirements.txt — a separate venv from admin.spec's, so admin-only
dependencies (SQLAlchemy, psycopg, alembic, argon2-cffi) are never importable
during this build. The excludes list below documents that invariant
explicitly rather than relying solely on the venv boundary.
"""

import pathlib

SPEC_DIR = pathlib.Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent.parent
POS_ROOT = REPO_ROOT / "apps" / "pos"
POS_SRC = POS_ROOT / "src"
ICON_PATH = REPO_ROOT / "packaging" / "assets" / "icon" / "fishshop.ico"
VERSION_INFO = SPEC_DIR / "version_info" / "pos_version_info.txt"

block_cipher = None

a = Analysis(
    [str(POS_SRC / "main.py")],
    pathex=[str(POS_SRC)],
    binaries=[],
    datas=[
        (str(POS_ROOT / ".env.example"), "."),
        (str(ICON_PATH), "."),
    ],
    hiddenimports=[
        "PySide6.QtNetwork",
        "PySide6.QtPrintSupport",
        "win32print",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineWidgets",
        "sqlalchemy",
        "psycopg",
        "alembic",
        "argon2",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_kwargs = {}
if VERSION_INFO.is_file():
    exe_kwargs["version"] = str(VERSION_INFO)
if ICON_PATH.is_file():
    exe_kwargs["icon"] = str(ICON_PATH)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FishShopPOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    **exe_kwargs,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FishShopPOS",
)
