"""Entry point for FishShopMigrate.exe — a frozen, Python-free Alembic runner
and test-data seeder.

The target machine has no Python installed, so `alembic upgrade head` cannot
be invoked directly. This CLI is bundled by migrate.spec against apps/admin's
migrations/, alembic.ini, models/, and security.py, and exposes the subset of
commands the installer needs:

  FishShopMigrate.exe upgrade head        - apply pending migrations
  FishShopMigrate.exe current             - show current DB revision
  FishShopMigrate.exe history              - show migration history
  FishShopMigrate.exe seed-test-users      - idempotently create the two
                                             fixed test accounts (see below)

It does not import anything from apps/pos and never runs implicitly —
packaging/scripts/migrate_database.ps1 is the only caller, invoked as an
explicit, operator-visible installer step.

seed-test-users creates exactly two accounts, for local testing/demo use
only (never for production distribution — see docs/packaging/windows-packaging.md):
  - username "test",  password "test", role ADMIN    (FishShop Admin login)
  - username "test1", password "test", role EMPLOYEE (FishShop POS login)
It is idempotent: if a username already exists, that row is left untouched
(never overwritten, never re-created) — safe to run on every install/upgrade.
"""

from __future__ import annotations

import sys
import traceback
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        # sys._MEIPASS is PyInstaller's own runtime attribute for the base
        # directory that datas=[...] files (alembic.ini, migrations/) were
        # extracted to - the only version-proof way to find them. Since
        # PyInstaller 6.0 (pinned as a minimum in build-requirements.txt),
        # onedir builds move everything except the .exe itself into an
        # `_internal/` subdirectory, so assuming bundled files sit next to
        # the .exe (Path(sys.executable).parent) breaks silently with
        # Alembic's "Path doesn't exist: ...\migrations".
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Running from source (e.g. local testing of this script): fall back to
    # the real apps/admin project directory.
    return Path(__file__).resolve().parent.parent.parent / "apps" / "admin"


def _add_admin_src_to_path() -> Path:
    root = _bundle_root()
    admin_src = root if getattr(sys, "frozen", False) else root / "src"
    if str(admin_src) not in sys.path:
        sys.path.insert(0, str(admin_src))
    return root


def _load_alembic_config() -> Config:
    root = _add_admin_src_to_path()
    from config import load_settings  # imported after sys.path is set up

    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", load_settings().database_url)
    return cfg


_ALEMBIC_COMMANDS = {
    "upgrade": lambda cfg, args: command.upgrade(cfg, args[0] if args else "head"),
    "downgrade": lambda cfg, args: command.downgrade(cfg, args[0] if args else "-1"),
    "current": lambda cfg, args: command.current(cfg, verbose=True),
    "history": lambda cfg, args: command.history(cfg),
}


def _seed_test_users() -> None:
    _add_admin_src_to_path()
    from config import load_settings
    from db import create_session_factory
    from models import Role, User
    from security import hash_password

    settings = load_settings()
    session_factory = create_session_factory(settings)

    seed_accounts = [
        ("test", "test", Role.ADMIN, "Test Admin"),
        ("test1", "test", Role.EMPLOYEE, "Test POS User"),
    ]

    with session_factory() as session:
        for username, password, role, full_name in seed_accounts:
            existing = session.query(User).filter_by(username=username).one_or_none()
            if existing is not None:
                print(f"User '{username}' already exists — leaving it unchanged.")
                continue
            session.add(
                User(
                    id=uuid.uuid4(),
                    username=username,
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=role,
                    is_active=True,
                )
            )
            print(f"Created test user '{username}' (role {role.value}).")
        session.commit()


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(
            "Usage: FishShopMigrate.exe <upgrade|downgrade|current|history|seed-test-users> [args]",
            file=sys.stderr,
        )
        return 2

    command_name, rest = argv[0], argv[1:]

    if command_name not in _ALEMBIC_COMMANDS and command_name != "seed-test-users":
        print(f"Unknown command: {command_name}", file=sys.stderr)
        return 2

    # Frozen (PyInstaller) executables never print a traceback for an
    # unhandled exception - the bootloader intercepts it and reports only
    # the generic "[PYI-7696:ERROR] Failed to execute script ... due to
    # unhandled exception!", hiding the actual Alembic/SQLAlchemy error.
    # Catch here and print the real cause so migrate_database.ps1's "See
    # output above for the Alembic error" has something concrete to show.
    try:
        if command_name == "seed-test-users":
            _seed_test_users()
        else:
            cfg = _load_alembic_config()
            _ALEMBIC_COMMANDS[command_name](cfg, rest)
    except Exception as exc:
        print(f"\nCommand '{command_name}' failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
