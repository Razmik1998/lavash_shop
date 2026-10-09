<#
.SYNOPSIS
    Admin-PC only. Idempotently installs/verifies PostgreSQL, waits until it
    actually accepts connections, and bootstraps the FishShop database role
    and database. Never drops or overwrites existing data - safe to run more
    than once (fresh install, repair, or upgrade).

.DESCRIPTION
    Passwords are accepted either as a literal value (-SuperPassword /
    -AppPassword, convenient for manual runs) or read from a file
    (-SuperPasswordFile / -AppPasswordFile). The installer always uses the
    file form: a password containing characters that are special to
    PowerShell ($, `, ", etc.) cannot survive being interpolated into a
    command line, so the secret is written to a temp file and only its path
    is passed as an argument.

    All SQL identifiers and literals are escaped with Format-PgIdentifier /
    Format-PgLiteral (common.ps1) before being interpolated into a -c
    statement, so a password or name containing quotes or other SQL-special
    characters is handled correctly instead of breaking (or injecting into)
    the statement. This is deliberately not psql's own -v name=value with
    :'var'/:"var" substitution: PowerShell rebuilds a single Win32 command
    line from the splatted argument array, and that step can mangle the
    embedded quotes those substitutions depend on before psql ever sees
    them - the observed failure mode is psql reporting "syntax error at or
    near ":"" because the value arrived without its surrounding quote.

.PARAMETER SuperPassword / SuperPasswordFile
    PostgreSQL superuser (postgres) password. Used for a fresh install and
    for connecting to bootstrap the role/database.

.PARAMETER AppPassword / AppPasswordFile
    Password to assign to the application role if it does not already exist.
    Never logged.

.PARAMETER DbName / RoleName / Port
    Defaults: shop_admin / shop_admin / 5432 (match apps/admin/.env.example).

.PARAMETER PostgresInstallerPath
    Optional. Path to an already-downloaded PostgreSQL Windows installer
    .exe, for offline/restricted machines. No download is attempted when set.

.PARAMETER DownloadUrl
    Optional. Override the default installer download URL (the default is a
    specific point release and can go stale - get a current URL from
    https://www.postgresql.org/download/windows/).
#>

param(
    [string]$SuperPassword,
    [string]$SuperPasswordFile,
    [string]$AppPassword,
    [string]$AppPasswordFile,
    [string]$DbName = "shop_admin",
    [string]$RoleName = "shop_admin",
    [int]$Port = 5432,
    [string]$PostgresInstallerPath,
    [string]$DownloadUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$TotalSteps = 6
$PgVersion = "16"
$script:LogPath = Start-FishShopScriptLog -ScriptName "install_database"
# Populated by the "locate client tools" step below; every psql/pg_isready
# call in this script goes through these full paths, never a bare command
# name, so behavior never depends on the operator's PATH being correct.
$script:PsqlExe = $null
$script:PgIsReadyExe = $null

function Resolve-Secret {
    param([string]$Literal, [string]$FromFile, [string]$Name)
    if ($FromFile) {
        if (-not (Test-Path $FromFile)) {
            throw "$Name file '$FromFile' does not exist."
        }
        # -Raw then trim only trailing newline: a password may legitimately
        # contain spaces, so do not Trim() whitespace generally.
        return (Get-Content $FromFile -Raw) -replace '\r?\n$', ''
    }
    return $Literal
}

function Get-PostgresService {
    return Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Wait-ForServiceRunning {
    param([Parameter(Mandatory = $true)][string]$ServiceName, [int]$TimeoutSeconds = 120)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -eq "Running") { return }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    throw "PostgreSQL service '$ServiceName' did not reach Running state within $TimeoutSeconds seconds."
}

function Wait-ForPostgresAcceptingConnections {
    # A Running service is not the same as a server ready to accept
    # connections - on a fresh install the cluster is still initialising for
    # a while after the service reports Running. Poll until a real
    # connection succeeds, so migrations never start against a server that
    # is not ready yet.
    param([int]$TimeoutSeconds = 180)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        if (Test-Path $script:PgIsReadyExe) {
            & $script:PgIsReadyExe -h localhost -p $Port -q 2>$null
            if ($LASTEXITCODE -eq 0) { return }
        }
        else {
            & $script:PsqlExe -U postgres -h localhost -p $Port -tAc "SELECT 1" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return }
        }
        Start-Sleep -Seconds 3
        $elapsed += 3
        Write-Host "  Waiting for PostgreSQL to accept connections... (${elapsed}s)"
    }
    throw "PostgreSQL did not start accepting connections on port $Port within $TimeoutSeconds seconds."
}

function Invoke-Psql {
    # Runs psql (via the resolved full path - see Resolve-PostgresBinDir,
    # never a bare "psql" that depends on PATH) and throws on failure,
    # surfacing psql's own stderr.
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Context
    )
    $output = & $script:PsqlExe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed: $output"
    }
    return $output
}

try {
    $superSecret = Resolve-Secret -Literal $SuperPassword -FromFile $SuperPasswordFile -Name "SuperPassword"
    $appSecret = Resolve-Secret -Literal $AppPassword -FromFile $AppPasswordFile -Name "AppPassword"
    if (-not $appSecret) {
        throw "An application role password is required (pass -AppPassword or -AppPasswordFile)."
    }

    # [1/6] Detect existing PostgreSQL
    Write-Step 1 $TotalSteps "Detecting existing PostgreSQL installation..."
    $service = Get-PostgresService
    $alreadyInstalled = $false
    if ($service -and $service.Status -eq "Running") {
        Write-Host "  PostgreSQL already installed and running: $($service.Name)"
        $alreadyInstalled = $true
    }
    elseif ($service) {
        Write-Host "  PostgreSQL service '$($service.Name)' found but not running; starting it..."
        Start-Service -Name $service.Name
        Wait-ForServiceRunning -ServiceName $service.Name
        $alreadyInstalled = $true
    }

    # [2/6] Install PostgreSQL if absent
    if (-not $alreadyInstalled) {
        Write-Step 2 $TotalSteps "Installing PostgreSQL $PgVersion..."
        if (-not $superSecret) {
            throw "PostgreSQL is not installed and no superuser password was provided (-SuperPassword/-SuperPasswordFile)."
        }

        if ($PostgresInstallerPath) {
            Write-Host "  Using provided installer: $PostgresInstallerPath"
            if (-not (Test-Path $PostgresInstallerPath)) {
                throw "-PostgresInstallerPath '$PostgresInstallerPath' does not exist."
            }
            $installerPath = $PostgresInstallerPath
        }
        elseif (Test-CommandExists "choco") {
            Write-Host "  Installing via Chocolatey..."
            & choco install postgresql$PgVersion -y --params "/Password:$superSecret" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Chocolatey PostgreSQL install failed (exit code $LASTEXITCODE)." }
            $installerPath = $null
        }
        else {
            Write-Host "  Chocolatey not found; downloading the official PostgreSQL installer..."
            $installerUrl = if ($DownloadUrl) { $DownloadUrl } else { "https://get.enterprisedb.com/postgresql/postgresql-$PgVersion.4-1-windows-x64.exe" }
            $installerPath = Join-Path $env:TEMP "postgresql-$PgVersion-installer.exe"
            try {
                Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
            }
            catch {
                throw ("Failed to download PostgreSQL installer from '$installerUrl': $($_.Exception.Message). " +
                    "This URL is a specific point release and can go stale, or this machine may have no internet " +
                    "access. Fix by either: (1) re-running with -DownloadUrl pointing at a current installer from " +
                    "https://www.postgresql.org/download/windows/, or (2) downloading that installer manually and " +
                    "re-running with -PostgresInstallerPath <path-to-downloaded-exe>.")
            }
        }

        if ($installerPath) {
            Write-Host "  Running the PostgreSQL installer (this can take several minutes)..."
            $proc = Start-Process -FilePath $installerPath -Wait -PassThru -ArgumentList @(
                "--mode", "unattended",
                "--unattendedmodeui", "minimal",
                "--superpassword", $superSecret,
                "--servicename", "postgresql-x64-$PgVersion",
                "--serverport", "$Port"
            )
            if ($proc.ExitCode -ne 0) {
                throw "PostgreSQL silent installer failed (exit code $($proc.ExitCode))."
            }
        }

        $service = Get-PostgresService
        if (-not $service) { throw "PostgreSQL installation completed but no postgresql* service was found." }
        Wait-ForServiceRunning -ServiceName $service.Name
    }
    else {
        Write-Step 2 $TotalSteps "PostgreSQL already installed - skipping install step."
    }

    # [3/6] Locate the PostgreSQL client tools and repair PATH (common.ps1's
    # Resolve-PostgresToolsOrThrow). This never trusts that "psql"/
    # "pg_isready" are already resolvable - it finds the real install
    # directory and every call below uses that full path directly, and also
    # fixes SYSTEM PATH so future sessions/re-runs don't hit this again.
    Write-Step 3 $TotalSteps "Locating PostgreSQL $PgVersion client tools..."
    $pgTools = Resolve-PostgresToolsOrThrow -Version $PgVersion
    $script:PsqlExe = $pgTools.Psql
    $script:PgIsReadyExe = $pgTools.PgIsReady

    # [4/6] Wait until the server actually accepts connections
    Write-Step 4 $TotalSteps "Waiting for PostgreSQL to accept connections..."
    $env:PGPASSWORD = $superSecret
    Wait-ForPostgresAcceptingConnections

    # [5/6] Idempotent role/database bootstrap.
    # Every identifier/literal is escaped with Format-PgIdentifier /
    # Format-PgLiteral (see the module docstring for why this is used
    # instead of psql's own -v/:'var' substitution) so special characters in
    # the password or names cannot break or inject into the statement.
    Write-Step 5 $TotalSteps "Bootstrapping role '$RoleName' and database '$DbName' (idempotent)..."

    $roleLiteral = Format-PgLiteral $RoleName
    $roleIdent = Format-PgIdentifier $RoleName
    $dbLiteral = Format-PgLiteral $DbName
    $dbIdent = Format-PgIdentifier $DbName
    $passLiteral = Format-PgLiteral $appSecret

    $roleExists = (Invoke-Psql -Context "Role existence check" -Arguments @(
            "-U", "postgres", "-h", "localhost", "-p", "$Port",
            "-tAc", "SELECT 1 FROM pg_roles WHERE rolname = $roleLiteral"
        ) | Out-String).Trim()

    if ($roleExists -ne "1") {
        Write-Host "  Creating role '$RoleName'..."
        Invoke-Psql -Context "Create role" -Arguments @(
            "-U", "postgres", "-h", "localhost", "-p", "$Port",
            "-c", "CREATE ROLE $roleIdent LOGIN PASSWORD $passLiteral"
        ) | Out-Null
    }
    else {
        Write-Host "  Role '$RoleName' already exists - leaving it unchanged."
    }

    $dbExists = (Invoke-Psql -Context "Database existence check" -Arguments @(
            "-U", "postgres", "-h", "localhost", "-p", "$Port",
            "-tAc", "SELECT 1 FROM pg_database WHERE datname = $dbLiteral"
        ) | Out-String).Trim()

    if ($dbExists -ne "1") {
        Write-Host "  Creating database '$DbName'..."
        Invoke-Psql -Context "Create database" -Arguments @(
            "-U", "postgres", "-h", "localhost", "-p", "$Port",
            "-c", "CREATE DATABASE $dbIdent OWNER $roleIdent"
        ) | Out-Null
    }
    else {
        Write-Host "  Database '$DbName' already exists - leaving it (and its data) unchanged."
    }

    # [6/6] Confirm the application role can actually connect to its database
    Write-Step 6 $TotalSteps "Verifying the application role can connect..."
    $env:PGPASSWORD = $appSecret
    Invoke-Psql -Context "Application role connection check" -Arguments @(
        "-U", $RoleName, "-h", "localhost", "-p", "$Port", "-d", $DbName, "-tAc", "SELECT 1"
    ) | Out-Null
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

    Write-Host "Database setup complete - PostgreSQL is running, role and database exist, and the role can connect."
}
catch {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
    Write-Error "Database installation failed: $($_.Exception.Message)"
    Write-Host "Full log saved to: $script:LogPath"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
