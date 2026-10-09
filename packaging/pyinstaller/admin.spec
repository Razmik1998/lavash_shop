# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FishShopAdmin.exe.

Built from packaging/.build-venv-admin (see packaging/scripts/build_windows.ps1),
which installs apps/admin/requirements.txt + packaging/pyinstaller/build-requirements.txt.
All paths below are resolved relative to this spec file's own location
(SPECPATH, injected by PyInstaller) so the build works from any checkout path.
"""

import pathlib

SPEC_DIR = pathlib.Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent.parent
ADMIN_ROOT = REPO_ROOT / "apps" / "admin"
ADMIN_SRC = ADMIN_ROOT / "src"
ICON_PATH = REPO_ROOT / "packaging" / "assets" / "icon" / "fishshop.ico"
VERSION_INFO = SPEC_DIR / "version_info" / "admin_version_info.txt"

block_cipher = None

a = Analysis(
    [str(ADMIN_SRC / "main.py")],
    pathex=[str(ADMIN_SRC)],
    binaries=[],
    datas=[
        (str(ADMIN_ROOT / "alembic.ini"), "."),
        (str(ADMIN_ROOT / "migrations"), "migrations"),
        (str(ADMIN_ROOT / ".env.example"), "."),
        (str(ICON_PATH), "."),
    ],
    hiddenimports=[
        "sqlalchemy.sql.default_comparator",
        "sqlalchemy.dialects.postgresql",
        "sqlalchemy.dialects.postgresql.psycopg",
        "sqlalchemy.dialects.postgresql.pg_catalog",
        "psycopg",
        "psycopg_binary",
        "psycopg.pq",
        "argon2",
        "_cffi_backend",
        "PySide6.QtNetwork",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineWidgets",
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
    name="FishShopAdmin",
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
    name="FishShopAdmin",
)
