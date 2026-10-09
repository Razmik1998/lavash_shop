<#
.SYNOPSIS
    Builds FishShopAdmin.exe, FishShopPOS.exe, FishShopMigrate.exe, and the
    final FishShopSetup-X.Y.Z.exe installer, from a clean checkout.

.DESCRIPTION
    Run from anywhere:
        powershell -ExecutionPolicy Bypass -File packaging\scripts\build_windows.ps1

    On any failure this script exits non-zero and does not produce a
    release/ artifact - see .claude/skills/packaging/build.md ("do not
    produce a fake successful release").

.PARAMETER Clean
    Force recreation of all three build virtual environments even if they
    already exist.
#>

param(
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$RepoRoot = Get-RepoRoot
$PackagingDir = Join-Path $RepoRoot "packaging"
$PyInstallerDir = Join-Path $PackagingDir "pyinstaller"
$InstallerDir = Join-Path $PackagingDir "installer"
$DistDir = Join-Path $PackagingDir "dist"
$BuildDir = Join-Path $PackagingDir "build"
$ReleaseDir = Join-Path $RepoRoot "release"

$TotalSteps = 8

function Resolve-Iscc {
    if (Test-CommandExists "ISCC.exe") {
        return (Get-Command "ISCC.exe").Source
    }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or add ISCC.exe to PATH."
}

function New-VersionTuple([string]$Version) {
    $parts = $Version.Split(".")
    return "$($parts[0]), $($parts[1]), $($parts[2]), 0"
}

function Test-PythonVersionSupported([string]$PythonExe) {
    # The pinned dependencies (PySide6, psycopg[binary], argon2-cffi) ship
    # prebuilt wheels only for released Python versions. A brand-new Python
    # (e.g. whatever "latest" installs the week it ships) typically has no
    # wheels yet, and pip then tries to build from source and fails. Restrict
    # the build to versions known to have wheels for these pins.
    try {
        $raw = & $PythonExe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    }
    catch {
        return $false
    }
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $false }
    return ($raw.Trim() -in @("3.12", "3.13"))
}

function Resolve-BuildPython {
    # Prefer an explicitly-versioned interpreter via the Windows py launcher,
    # so the build does not silently pick up an unsupported "latest" Python.
    foreach ($ver in @("3.12", "3.13")) {
        if (Test-CommandExists "py") {
            & py "-$ver" -c "pass" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Using Python $ver via the py launcher."
                return @("py", "-$ver")
            }
        }
    }
    if ((Test-CommandExists "python") -and (Test-PythonVersionSupported "python")) {
        Write-Host "  Using 'python' from PATH."
        return @("python")
    }
    throw ("No supported Python found. This build requires Python 3.12 or 3.13 - the pinned " +
        "dependencies (PySide6, psycopg[binary], argon2-cffi) do not have prebuilt wheels for " +
        "newer Python versions yet, so pip would try to compile them from source and fail. " +
        "Install Python 3.12 or 3.13 from https://www.python.org/downloads/windows/ (tick " +
        "'Add python.exe to PATH'), then re-run this script.")
}

function Invoke-BuildVenv {
    param(
        [Parameter(Mandatory = $true)][string]$VenvPath,
        [Parameter(Mandatory = $true)][string[]]$RequirementsFiles
    )
    if ($Clean -and (Test-Path $VenvPath)) {
        Remove-Item -Recurse -Force $VenvPath
    }
    if (-not (Test-Path $VenvPath)) {
        $pythonCmd = $script:BuildPython[0]
        $pythonArgs = @()
        if ($script:BuildPython.Count -gt 1) { $pythonArgs = $script:BuildPython[1..($script:BuildPython.Count - 1)] }
        & $pythonCmd @pythonArgs -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment at $VenvPath" }
    }
    $python = Join-Path $VenvPath "Scripts\python.exe"
    & $python -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in $VenvPath" }
    $pipArgs = @("-m", "pip", "install", "--quiet")
    foreach ($req in $RequirementsFiles) { $pipArgs += @("-r", $req) }
    & $python @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed for $VenvPath (requirements: $($RequirementsFiles -join ', '))" }
}

try {
    # [1/8] Clean previous build artifacts
    Write-Step 1 $TotalSteps "Cleaning previous build/dist/release artifacts..."
    foreach ($dir in @($BuildDir, $DistDir, $ReleaseDir)) {
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    }
    $generatedVersionIss = Join-Path $InstallerDir "version.iss"
    if (Test-Path $generatedVersionIss) { Remove-Item -Force $generatedVersionIss }
    foreach ($name in @("admin_version_info.txt", "pos_version_info.txt", "migrate_version_info.txt")) {
        $generated = Join-Path $PyInstallerDir "version_info\$name"
        if (Test-Path $generated) { Remove-Item -Force $generated }
    }

    # [2/8] Resolve version and build interpreter, render templates
    Write-Step 2 $TotalSteps "Resolving version, build interpreter, and rendering templates..."
    $script:BuildPython = Resolve-BuildPython
    $Version = Get-FishShopVersion
    $VersionTuple = New-VersionTuple $Version
    Write-Host "  Version: $Version"

    $versionIssTemplate = Join-Path $InstallerDir "version.iss.template"
    (Get-Content $versionIssTemplate -Raw).Replace("@VERSION@", $Version) |
        Set-Content -Path $generatedVersionIss -Encoding UTF8

    foreach ($name in @("admin", "pos", "migrate")) {
        $template = Join-Path $PyInstallerDir "version_info\${name}_version_info.txt.template"
        $rendered = Join-Path $PyInstallerDir "version_info\${name}_version_info.txt"
        (Get-Content $template -Raw).Replace("@VERSION_TUPLE@", $VersionTuple).Replace("@VERSION_STR@", $Version) |
            Set-Content -Path $rendered -Encoding UTF8
    }

    # [3/8] Admin build venv
    Write-Step 3 $TotalSteps "Creating/refreshing Admin build virtual environment..."
    $adminVenv = Join-Path $PackagingDir ".build-venv-admin"
    Invoke-BuildVenv -VenvPath $adminVenv -RequirementsFiles @(
        (Join-Path $RepoRoot "apps\admin\requirements.txt"),
        (Join-Path $PyInstallerDir "build-requirements.txt")
    )

    # [4/8] POS build venv
    Write-Step 4 $TotalSteps "Creating/refreshing POS build virtual environment..."
    $posVenv = Join-Path $PackagingDir ".build-venv-pos"
    Invoke-BuildVenv -VenvPath $posVenv -RequirementsFiles @(
        (Join-Path $RepoRoot "apps\pos\requirements.txt"),
        (Join-Path $PyInstallerDir "build-requirements.txt")
    )

    # [5/8] Migrate build venv
    Write-Step 5 $TotalSteps "Creating/refreshing Migrate build virtual environment..."
    $migrateVenv = Join-Path $PackagingDir ".build-venv-migrate"
    Invoke-BuildVenv -VenvPath $migrateVenv -RequirementsFiles @(
        (Join-Path $PyInstallerDir "migrate-requirements.txt"),
        (Join-Path $PyInstallerDir "build-requirements.txt")
    )

    # [6/8] Run PyInstaller for all three targets
    Write-Step 6 $TotalSteps "Building FishShopAdmin, FishShopPOS, and FishShopMigrate..."
    $pyinstallerCommonArgs = @("--noconfirm", "--clean", "--distpath", $DistDir, "--workpath", $BuildDir)

    & (Join-Path $adminVenv "Scripts\pyinstaller.exe") @pyinstallerCommonArgs (Join-Path $PyInstallerDir "admin.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed building FishShopAdmin" }

    & (Join-Path $posVenv "Scripts\pyinstaller.exe") @pyinstallerCommonArgs (Join-Path $PyInstallerDir "pos.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed building FishShopPOS" }

    & (Join-Path $migrateVenv "Scripts\pyinstaller.exe") @pyinstallerCommonArgs (Join-Path $PyInstallerDir "migrate.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed building FishShopMigrate" }

    # [7/8] Validate build outputs
    Write-Step 7 $TotalSteps "Validating executables exist..."
    $adminExe = Join-Path $DistDir "FishShopAdmin\FishShopAdmin.exe"
    $posExe = Join-Path $DistDir "FishShopPOS\FishShopPOS.exe"
    $migrateExe = Join-Path $DistDir "FishShopMigrate\FishShopMigrate.exe"
    Assert-FileExists -Path $adminExe -Context "FishShopAdmin build"
    Assert-FileExists -Path $posExe -Context "FishShopPOS build"
    Assert-FileExists -Path $migrateExe -Context "FishShopMigrate build"

    # [8/8] Build the installer
    Write-Step 8 $TotalSteps "Building Windows installer with Inno Setup..."
    $iscc = Resolve-Iscc
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    & $iscc (Join-Path $InstallerDir "FishShop.iss") "/O$ReleaseDir" "/FFishShopSetup-$Version"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }

    $installerPath = Join-Path $ReleaseDir "FishShopSetup-$Version.exe"
    Assert-FileExists -Path $installerPath -Context "Installer build"

    Write-Host ""
    Write-Host "Build completed."
    Write-Host "  Version:          $Version"
    Write-Host "  Admin executable: $adminExe"
    Write-Host "  POS executable:   $posExe"
    Write-Host "  Installer output: $installerPath"
}
catch {
    Write-Error "Build failed: $($_.Exception.Message)"
    exit 1
}
