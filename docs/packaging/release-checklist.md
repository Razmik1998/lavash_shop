# Windows Clean-Machine Release Checklist

This checklist requires real Windows hardware or VMs. It cannot be executed
from a non-Windows development environment, and no release should be
declared "done" until it has been run — per this repo's own
`.claude/skills/packaging/build.md` ("verify the frozen build actually
launches and connects to the database/LAN service on a clean machine/VM
before considering a release build complete").

## Prerequisites for the test machine(s)

The test machine(s) must **not** have installed: Python, pip, Poetry,
virtualenv, PyInstaller, Git, or a checkout of this repository. The only
artifact needed is `FishShopSetup-<version>.exe`.

## Checklist

- [ ] `packaging\scripts\build_windows.ps1` runs end-to-end on a Windows
      build machine and produces `release\FishShopSetup-<version>.exe`
      with no errors.
- [ ] Installer launches on a clean Windows VM.
- [ ] Admin PC install completes: `FishShopAdmin.exe`, `FishShopPOS.exe`,
      and PostgreSQL are all installed.
- [ ] PostgreSQL service is running; `install_database.ps1` correctly
      detected "not installed" on a truly clean machine and installed it
      (test both the Chocolatey path and the direct EnterpriseDB-installer
      fallback path, on separate clean VMs if possible).
- [ ] `shop_admin` role and `shop_admin` database were created.
- [ ] Alembic migrations ran (`migrate_database.ps1` /
      `FishShopMigrate.exe upgrade head`) and brought the schema from empty
      to head with no errors.
- [ ] FishShop Admin starts, connects to PostgreSQL, and its LAN TCP server
      is reachable.
- [ ] POS PC install (separate clean VM) completes with only
      `FishShopPOS.exe` installed, `ADMIN_HOST`/`ADMIN_PORT` pointed at the
      Admin VM's real LAN address, and a unique `POS_TERMINAL_ID`.
- [ ] FishShop POS starts, successfully reaches the Admin server, completes
      a login and a full sale, and writes a receipt PDF into
      `%ProgramData%\FishShop\data\receipts\`.
- [ ] Start Menu shortcuts work for both apps.
- [ ] Desktop shortcuts, if the corresponding task was checked, work for
      both apps.
- [ ] Launch-after-install checkboxes work independently; both apps are
      never launched simultaneously by the installer.
- [ ] Re-running `FishShopSetup-<version>.exe` on an already-installed
      machine does not duplicate database records, drop tables, destroy
      data, recreate the role/database, or break the PostgreSQL service.
- [ ] Uninstall removes only the installed program files —
      `%ProgramData%\FishShop` (config, receipts) and the PostgreSQL data
      directory survive.
- [ ] Full upgrade cycle: install `X.Y.Z`, add real data, build and install
      `X.Y.(Z+1)` over it — binaries are replaced, configuration and
      database survive, migrations run, the new version starts correctly,
      with no duplicate Start Menu entries.
- [ ] (Optional but recommended) Confirm via packet capture that a
      cross-machine POS-to-Admin login is indeed unencrypted today — this
      is a known, accepted risk (see `windows-packaging.md`), not something
      this checklist should try to "fix."

## Release report template

```
FishShop Windows Release Report
================================
Build command:        packaging\scripts\build_windows.ps1
Installer output:      release\FishShopSetup-<X.Y.Z>.exe  (size: ___ MB)
Admin exe:              packaging\dist\FishShopAdmin\FishShopAdmin.exe  (version: <X.Y.Z>)
POS exe:                packaging\dist\FishShopPOS\FishShopPOS.exe      (version: <X.Y.Z>)
Version:                <X.Y.Z>
Migration status:       alembic upgrade head -> <head revision id>, exit code 0
Clean Windows test status:
  Admin PC install:     PASS/FAIL - details
  POS PC install:       PASS/FAIL - details
  Upgrade-in-place:     PASS/FAIL - details
  Uninstall data-preservation: PASS/FAIL - details
Known risks accepted:   POS-to-Admin auth is plaintext over LAN when
                        ADMIN_HOST is non-loopback (see windows-packaging.md)
```
