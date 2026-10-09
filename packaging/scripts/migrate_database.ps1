<#
.SYNOPSIS
    Admin-PC only. Waits for the database to be reachable, then runs Alembic
    migrations (via the bundled FishShopMigrate.exe) and optionally seeds the
    fixed test accounts - all as explicit, operator-visible steps. Never
    invoked implicitly by FishShopAdmin.exe at startup. Safe to re-run:
    `alembic upgrade head` is a no-op once the schema is current, and seeding
    skips any account that already exists.

.PARAMETER InstallDir
    Root install directory. FishShopMigrate.exe is expected at
    "$InstallDir\Admin\FishShopMigrate.exe".

.PARAMETER SkipSeed
    Skip creating the built-in test accounts (test/test and test1/test).
    Use this for a real production deployment - those accounts exist for
    local testing/demo only.
#>

param(
    [string]$InstallDir = "$env:ProgramFiles\FishShop",
    [switch]$SkipSeed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$TotalSteps = 4
$PgVersion = "16"
$script:LogPath = Start-FishShopScriptLog -ScriptName "migrate_database"

function Wait-ForDatabaseReachable {
    # The migration runner connects through DATABASE_URL; make sure the
    # server is actually accepting connections before starting, so a slow
    # PostgreSQL startup doesn't surface as a confusing migration failure.
    # Resolves pg_isready.exe by full path (common.ps1's
    # Resolve-PostgresBinDir) rather than trusting PATH, same fix as
    # install_database.ps1 - this is a best-effort preflight, though, so a
    # missing pg_isready only skips the poll rather than failing the run.
    param([int]$TimeoutSeconds = 180)
    $binDir = Resolve-PostgresBinDir -Version $PgVersion
    if (-not $binDir) {
        Write-Host "  PostgreSQL $PgVersion client tools not found - skipping pre-flight reachability poll."
        return
    }
    $pgIsReadyExe = Join-Path $binDir "pg_isready.exe"
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        & $pgIsReadyExe -h localhost -q 2>$null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 3
        $elapsed += 3
        Write-Host "  Waiting for the database to become reachable... (${elapsed}s)"
    }
    throw "Database was not reachable within $TimeoutSeconds seconds - cannot run migrations."
}

try {
    # [1/4] Locate FishShopMigrate.exe
    Write-Step 1 $TotalSteps "Locating FishShopMigrate.exe..."
    $migrateExe = Join-Path $InstallDir "Admin\FishShopMigrate.exe"
    Assert-FileExists -Path $migrateExe -Context "Migration runner"

    # [2/4] Verify configuration is present and the server is up
    Write-Step 2 $TotalSteps "Verifying production configuration and database availability..."
    $configEnv = Join-Path (Get-FishShopConfigDir) ".env"
    if (-not (Test-Path $configEnv)) {
        throw "Configuration not found at $configEnv - run configure_environment.ps1 -Role Admin first."
    }
    $values = Read-DotEnvFile -Path $configEnv
    if (-not $values.Contains("DATABASE_URL") -or -not $values["DATABASE_URL"]) {
        throw "DATABASE_URL is not set in $configEnv - run configure_environment.ps1 -Role Admin first."
    }
    Wait-ForDatabaseReachable

    # [3/4] Run migrations, explicitly and visibly
    Write-Step 3 $TotalSteps "Applying database migrations (alembic upgrade head)..."
    & $migrateExe upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "FishShopMigrate.exe upgrade head failed (exit code $LASTEXITCODE). See output above for the Alembic error."
    }
    Write-Host "  Migrations applied. Current revision:"
    & $migrateExe current

    # [4/4] Seed the built-in test accounts (idempotent)
    if ($SkipSeed) {
        Write-Step 4 $TotalSteps "Skipping test account seeding (-SkipSeed)."
    }
    else {
        Write-Step 4 $TotalSteps "Creating test accounts (idempotent; existing accounts are left unchanged)..."
        & $migrateExe seed-test-users
        if ($LASTEXITCODE -ne 0) {
            throw "FishShopMigrate.exe seed-test-users failed (exit code $LASTEXITCODE)."
        }
        Write-Host ""
        Write-Host "  Test accounts available:"
        Write-Host "    FishShop Admin: username 'test'  password 'test'"
        Write-Host "    FishShop POS:   username 'test1' password 'test'"
        Write-Host "  These are for testing/demo only - remove them before real production use."
    }

    Write-Host "Database migration step complete."
}
catch {
    Write-Error "Database migration failed: $($_.Exception.Message)"
    Write-Host "Full log saved to: $script:LogPath"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
