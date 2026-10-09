<#
.SYNOPSIS
    Shared helpers dot-sourced by every FishShop packaging/installer script.
    Not runnable standalone.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    # packaging/scripts/common.ps1 -> packaging -> repo root
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-FishShopVersion {
    $versionFile = Join-Path (Get-RepoRoot) "VERSION"
    if (-not (Test-Path $versionFile)) {
        throw "VERSION file not found at $versionFile"
    }
    $version = (Get-Content $versionFile -Raw).Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+$') {
        throw "VERSION file content '$version' is not a valid X.Y.Z version string"
    }
    return $version
}

function Write-Step {
    param(
        [Parameter(Mandatory = $true)][int]$Current,
        [Parameter(Mandatory = $true)][int]$Total,
        [Parameter(Mandatory = $true)][string]$Message
    )
    Write-Host "[$Current/$Total] $Message"
}

function Test-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Resolve-PostgresBinDir {
    # Finds the PostgreSQL client tools directory without ever assuming
    # PATH is already correct. Tried in order:
    #   1. The default install location for this version (covers the
    #      overwhelming majority of installs - default installer, choco).
    #   2. The registry key every official EDB installer writes, which
    #      records the *actual* install directory - covers a custom
    #      install path.
    #   3. `psql.exe` already resolvable on the current PATH (covers a
    #      prior manual setup this script didn't perform).
    # Returns the bin directory, or $null if none of the above found it.
    param([Parameter(Mandatory = $true)][string]$Version)

    $defaultBin = Join-Path "$env:ProgramFiles\PostgreSQL\$Version" "bin"
    if (Test-Path (Join-Path $defaultBin "psql.exe")) {
        return $defaultBin
    }

    $regRoot = "HKLM:\SOFTWARE\PostgreSQL\Installations"
    if (Test-Path $regRoot) {
        foreach ($key in Get-ChildItem $regRoot -ErrorAction SilentlyContinue) {
            if ($key.PSChildName -notmatch [regex]::Escape($Version)) { continue }
            $baseDir = (Get-ItemProperty -Path $key.PSPath -ErrorAction SilentlyContinue).'Base Directory'
            if (-not $baseDir) { continue }
            $candidateBin = Join-Path $baseDir "bin"
            if (Test-Path (Join-Path $candidateBin "psql.exe")) {
                return $candidateBin
            }
        }
    }

    $onPath = Get-Command "psql.exe" -ErrorAction SilentlyContinue
    if ($onPath) {
        return (Split-Path $onPath.Source -Parent)
    }

    return $null
}

function Add-DirectoryToMachinePath {
    # Idempotently appends $Directory to the SYSTEM PATH so this fix
    # survives new sessions/terminals, not just the current process.
    # Returns $true if it changed anything.
    param([Parameter(Mandatory = $true)][string]$Directory)
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $normalized = ($machinePath -split ";") |
        Where-Object { $_ -and $_.Trim() -ne "" } |
        ForEach-Object { $_.Trim().TrimEnd("\") }
    if ($normalized -contains $Directory.TrimEnd("\")) {
        return $false
    }
    [Environment]::SetEnvironmentVariable("Path", "$machinePath;$Directory", "Machine")
    return $true
}

function Resolve-PostgresToolsOrThrow {
    # Locates the PostgreSQL bin dir for $Version, repairs both SYSTEM PATH
    # (survives future sessions) and the current process PATH (works
    # immediately), and returns @{ Psql = <path>; PgIsReady = <path> }.
    # Throws with a precise, actionable message if it cannot be found -
    # callers should never fall back to a bare "psql"/"pg_isready" call.
    param([Parameter(Mandatory = $true)][string]$Version)

    $binDir = Resolve-PostgresBinDir -Version $Version
    if (-not $binDir) {
        throw ("PostgreSQL $Version client tools (psql.exe) were not found in the default " +
            "install location ('$env:ProgramFiles\PostgreSQL\$Version\bin'), the registry, or PATH. " +
            "Verify PostgreSQL $Version is actually installed, or pass -PostgresInstallerPath to a known-good installer.")
    }
    Write-Host "  Found PostgreSQL client tools: $binDir"
    if (Add-DirectoryToMachinePath -Directory $binDir) {
        Write-Host "  Added to system PATH (takes effect in new sessions): $binDir"
    }
    else {
        Write-Host "  Already present in system PATH: $binDir"
    }
    if (($env:Path -split ";") -notcontains $binDir) {
        $env:Path = "$binDir;$env:Path"
    }
    return @{
        Psql      = Join-Path $binDir "psql.exe"
        PgIsReady = Join-Path $binDir "pg_isready.exe"
    }
}

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Context
    )
    if (-not (Test-Path $Path)) {
        throw "$Context - expected file was not created: $Path"
    }
}

function Get-FishShopConfigDir {
    $programData = $env:PROGRAMDATA
    if (-not $programData) { $programData = "C:\ProgramData" }
    return (Join-Path $programData "FishShop\config")
}

function Get-FishShopDataDir {
    $programData = $env:PROGRAMDATA
    if (-not $programData) { $programData = "C:\ProgramData" }
    return (Join-Path $programData "FishShop\data")
}

function Get-FishShopLogsDir {
    $programData = $env:PROGRAMDATA
    if (-not $programData) { $programData = "C:\ProgramData" }
    return (Join-Path $programData "FishShop\logs")
}

function Start-FishShopScriptLog {
    # Starts a full console transcript (every Write-Host/Write-Error/thrown
    # message) to a timestamped file, so the exact error from a failed
    # install/migration step survives after the console closes and can be
    # copied verbatim. Callers must pair this with Stop-Transcript in a
    # `finally` block. Returns the log file path.
    param([Parameter(Mandatory = $true)][string]$ScriptName)
    $logsDir = Get-FishShopLogsDir
    New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $logPath = Join-Path $logsDir "${ScriptName}_${timestamp}.log"
    Start-Transcript -Path $logPath -Append | Out-Null
    return $logPath
}

function Read-DotEnvFile {
    # Returns an ordered hashtable of KEY=VALUE pairs from a .env-style file.
    # Missing file returns an empty (ordered) hashtable - never throws.
    param([Parameter(Mandatory = $true)][string]$Path)
    $result = [ordered]@{}
    if (-not (Test-Path $Path)) {
        return $result
    }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        $result[$key] = $value
    }
    return $result
}

function Format-PgIdentifier {
    # Safely quotes a Postgres identifier (role/database/column name) for
    # interpolation into a -c string. Doubling embedded double quotes is the
    # standard SQL-identifier escape; this is used instead of psql's own
    # :"var" substitution because PowerShell's native-argument marshalling
    # (rebuilding a single Win32 command line from a splatted string array)
    # can mangle the embedded single/double quotes that :"var"/:'var" rely
    # on before psql ever sees them.
    param([Parameter(Mandatory = $true)][string]$Value)
    return '"' + ($Value -replace '"', '""') + '"'
}

function Format-PgLiteral {
    # Safely quotes a Postgres string literal (e.g. a password) for
    # interpolation into a -c string. Doubling embedded single quotes is the
    # standard SQL-literal escape. See Format-PgIdentifier for why this
    # replaces psql's :'var' substitution here.
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Write-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][System.Collections.Specialized.OrderedDictionary]$Values
    )
    $lines = foreach ($key in $Values.Keys) { "$key=$($Values[$key])" }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}
