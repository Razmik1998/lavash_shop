# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FishShopMigrate.exe.

A small console CLI (see migrate_entry.py) that runs Alembic migrations
against the production PostgreSQL database with no Python installed on the
target machine. Built from packaging/.build-venv-migrate, which installs only
the Alembic/SQLAlchemy/psycopg/python-dotenv subset of apps/admin/requirements.txt
(kept in sync with that file — no PySide6, no argon2-cffi). Invoked exclusively
by packaging/scripts/migrate_database.ps1 as an explicit, operator-visible step
(e.g. `FishShopMigrate.exe upgrade head`) — never run implicitly by
FishShopAdmin.exe at startup.
"""

import pathlib

SPEC_DIR = pathlib.Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent.parent
ADMIN_ROOT = REPO_ROOT / "apps" / "admin"
ADMIN_SRC = ADMIN_ROOT / "src"
VERSION_INFO = SPEC_DIR / "version_info" / "migrate_version_info.txt"

block_cipher = None

a = Analysis(
    [str(SPEC_DIR / "migrate_entry.py")],
    pathex=[str(ADMIN_SRC)],
    binaries=[],
    datas=[
        (str(ADMIN_ROOT / "alembic.ini"), "."),
        (str(ADMIN_ROOT / "migrations"), "migrations"),
    ],
    hiddenimports=[
        "sqlalchemy.sql.default_comparator",
        "sqlalchemy.dialects.postgresql",
        "sqlalchemy.dialects.postgresql.psycopg",
        "sqlalchemy.dialects.postgresql.pg_catalog",
        "psycopg",
        "psycopg_binary",
        "psycopg.pq",
        "alembic.op",
        "alembic.context",
        # apps/admin/migrations/env.py is loaded dynamically at runtime by
        # Alembic (importlib, not a normal import), so PyInstaller's static
        # analysis never sees its imports - anything it needs beyond what's
        # already listed here must be declared explicitly or it fails only
        # inside the frozen exe with "ModuleNotFoundError: No module named
        # 'logging.config'" (or similar) when `upgrade`/`downgrade` runs.
        "logging.config",
        # seed-test-users hashes passwords via apps/admin/src/security.py
        "argon2",
        "_cffi_backend",
        # imported dynamically by seed-test-users after sys.path setup
        "config",
        "db",
        "models",
        "security",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6"],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_kwargs = {}
if VERSION_INFO.is_file():
    exe_kwargs["version"] = str(VERSION_INFO)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FishShopMigrate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    name="FishShopMigrate",
)
