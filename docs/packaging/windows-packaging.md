# Windows Packaging Architecture

## Overview

`apps/admin` and `apps/pos` are independently-deployable PySide6 desktop
apps with no shared code. This packaging system produces a single Windows
installer, `FishShopSetup-<version>.exe`, that installs either or both of
them plus (on an Admin PC) PostgreSQL — with no Python required on the
target machine.

```
packaging/
├── pyinstaller/     admin.spec, pos.spec, migrate.spec + shared assets
├── installer/       FishShop.iss (Inno Setup)
├── assets/icon/     placeholder app icon
└── scripts/         *.ps1 build/install/migrate/configure scripts
```

## Three PyInstaller builds, not two

The task names only `FishShopAdmin.exe` and `FishShopPOS.exe`, but a third,
small console executable — **`FishShopMigrate.exe`** — is also built from
`packaging/pyinstaller/migrate.spec` + `migrate_entry.py`. It exists because
Alembic migrations (`alembic upgrade head`) must run as an explicit,
operator-visible installer step (see `.claude/skills/packaging/deployment.md`),
but the target machine has no Python interpreter at all. `FishShopMigrate.exe`
is a frozen, self-contained wrapper around Alembic's `upgrade`/`downgrade`/
`current`/`history` commands, invoked only by
`packaging/scripts/migrate_database.ps1` — never by `FishShopAdmin.exe`
itself.

## Separate build virtual environments

`build_windows.ps1` creates three build-only virtual environments —
`.build-venv-admin`, `.build-venv-pos`, `.build-venv-migrate` — installed
from each app's own pinned `requirements.txt` (the source of truth for
reproducible builds, not `pyproject.toml`'s open ranges) plus
`packaging/pyinstaller/build-requirements.txt` (PyInstaller itself). This
keeps the "no shared code" boundary intact at build time too: POS's spec
file additionally excludes `sqlalchemy`/`psycopg`/`alembic`/`argon2` as a
written-down invariant, on top of them being physically absent from that
venv.

## Config-loading changes

Both apps' `config.py` originally called bare `load_dotenv()`, which only
searches the current working directory and its parents — fine for
`python src/main.py` in a dev checkout, useless for an installed app
launched from a Start Menu shortcut with an unpredictable CWD. Both now
additionally load `%ProgramData%\FishShop\config\.env` if present
(`override=False`, so a real environment variable or a dev-mode `.env`
still wins). `configure_environment.ps1` writes that file.

`apps/pos/src/config.py`'s `RECEIPT_DIRECTORY` also gets a small addition:
when relative (the default, `"receipts"`) *and* the process is frozen
(`sys.frozen`), it resolves against `%ProgramData%\FishShop\data\receipts`
instead of an unpredictable CWD-relative path. Dev-mode behavior (CWD-relative)
is completely unchanged.

No UI, business logic, inventory/sales/sync/auth code was touched.

## Versioning

`VERSION` at the repo root is the single authored value. `build_windows.ps1`
renders it into `packaging/installer/version.iss` (from
`version.iss.template`, via `#include` in `FishShop.iss`) and into the three
`*_version_info.txt` files (from their `.template`s, used by PyInstaller's
`EXE(version=...)`) at build time. Bump `VERSION`, nothing else needs
changing, and `FishShopSetup-1.0.1.exe` falls out on the next build.

## Install topology

- **Admin PC** (`admin` install type): `FishShopAdmin.exe` + `FishShopPOS.exe`
  + `FishShopMigrate.exe` + PostgreSQL. Installer runs, in order:
  `install_database.ps1` (idempotent PostgreSQL install/role/db bootstrap) →
  `configure_environment.ps1 -Role Admin` → `migrate_database.ps1`.
- **POS PC** (`pos` install type): `FishShopPOS.exe` only. Installer prompts
  for the Admin machine's address/port (`ADMIN_HOST`/`ADMIN_PORT` — POS has
  no database of its own, so "database host/port" in the original task spec
  is interpreted as this LAN address) and a unique `POS_TERMINAL_ID`, then
  runs `configure_environment.ps1 -Role POS`.

Both apps' launch-after-install checkboxes are independent and
unchecked by default — the two apps are never auto-launched together.

Uninstall never deletes `%ProgramData%\FishShop` (configuration, receipts)
or PostgreSQL's own data directory — only the installed program files are
removed.

## Known, accepted risk (not fixed by this packaging work)

`apps/pos/src/networking/local_connection.py` is documented, by its own
module docstring, as a loopback-only, plaintext-by-design connection — any
future cross-machine connection was explicitly flagged there as requiring a
TLS-capable `LanConnection` first. This installer makes a real
cross-machine POS deployment configurable (`ADMIN_HOST` pointing at a LAN
address), which means today the login password would cross the LAN in
plaintext. Packaging is explicitly out of scope for touching authentication
logic, so this is a real, load-bearing gap this installer newly exposes in
practice — not a hypothetical — and should be tracked as follow-up work
before a genuine multi-machine deployment goes into production use.

## Test accounts

On an Admin install, the "Create test accounts" task (checked by default)
runs `FishShopMigrate.exe seed-test-users` after migrations, creating:

| Username | Password | Role     | Used for       |
|----------|----------|----------|----------------|
| `test`   | `test`   | ADMIN    | FishShop Admin |
| `test1`  | `test`   | EMPLOYEE | FishShop POS   |

Seeding is idempotent — an existing username is never overwritten. **These
are fixed, well-known credentials for testing/demo convenience only.**
Uncheck that task (or pass `-SkipSeed` to `migrate_database.ps1`) for a real
production deployment, and delete the accounts if they were already created.

## Handling of passwords and special characters

Two failure modes are handled explicitly, because both silently corrupt or
break a password containing characters like `$`, `` ` ``, `"`, `'`, `@` or `%`:

1. **Command lines.** The installer never interpolates the password into a
   PowerShell command line. It writes it to a temp file and passes only the
   path (`-AppPasswordFile` / `-SuperPasswordFile`); the file is deleted
   after the install steps run.
2. **SQL and URIs.** `install_database.ps1` passes every value through psql
   variables (`-v name=value` with `:'var'` / `:"var"` substitution) rather
   than string-concatenating into the statement, and
   `configure_environment.ps1` percent-encodes the password
   (`[uri]::EscapeDataString`) before embedding it in `DATABASE_URL`.

## Waiting for the database

A PostgreSQL service reporting `Running` is not the same as a server ready
to accept connections — on a fresh install the cluster is still
initialising. `install_database.ps1` polls with `pg_isready` (falling back
to a real `SELECT 1`) until connections succeed, then verifies the
application role itself can connect. `migrate_database.ps1` re-checks
reachability before running migrations, so a slow startup surfaces as an
explicit wait rather than a confusing migration error.

## Building

```powershell
powershell -ExecutionPolicy Bypass -File packaging\scripts\build_windows.ps1
```

Requires, on the build machine: **Python 3.12 or 3.13** and Inno Setup 6
(`ISCC.exe` on PATH or in its default install location).

The Python version matters: the pinned runtime dependencies (PySide6,
`psycopg[binary]`, argon2-cffi) publish prebuilt wheels only for released
Python versions, so a brand-new "latest" Python has no wheels yet and pip
falls back to compiling from source, which fails. `build_windows.ps1`
therefore resolves the interpreter explicitly (preferring the `py` launcher
with `-3.12`/`-3.13`) and refuses to build on an unsupported version with a
clear message rather than failing deep inside pip.

Produces `release/FishShopSetup-<version>.exe`. Any failure (missing tool,
failed `pip install`, missing executable, failed Inno Setup compile) exits
non-zero and does not produce a release artifact.
