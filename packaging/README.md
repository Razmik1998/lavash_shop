# FishShop Windows Packaging

To cut a release:

1. Bump the version number in `../VERSION` (repo root).
2. Run, on Windows, with Python 3.13+ and Inno Setup 6 installed:
   ```powershell
   powershell -ExecutionPolicy Bypass -File packaging\scripts\build_windows.ps1
   ```
3. Find the installer at `../release/FishShopSetup-<version>.exe`.

See [`../docs/packaging/windows-packaging.md`](../docs/packaging/windows-packaging.md)
for the full architecture (why there are three PyInstaller builds, how
config/versioning flow, and the config-loading changes made to both apps),
and [`../docs/packaging/release-checklist.md`](../docs/packaging/release-checklist.md)
for the manual clean-Windows-machine verification checklist that must be run
before any release is considered done.
