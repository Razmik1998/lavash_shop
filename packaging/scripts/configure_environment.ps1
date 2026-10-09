<#
.SYNOPSIS
    Writes/updates %ProgramData%\FishShop\config\.env for the given install
    role (Admin or POS), and ensures %ProgramData%\FishShop\data\receipts
    exists and is writable. Idempotent/upgrade-safe: on an existing .env,
    only adds missing keys or keys explicitly passed on this run - it never
    blindly overwrites the whole file, so prior operator configuration
    (store name, printer, etc.) survives an upgrade install.

.PARAMETER Role
    "Admin" or "POS".

.PARAMETER DatabaseUrl
    Admin only. Full SQLAlchemy DATABASE_URL. Required on first configure.

.PARAMETER AdminLanPort
    Admin only. Defaults to 8765.

.PARAMETER BusinessTimezone
    Admin only. Defaults to Asia/Yerevan.

.PARAMETER AdminHost / AdminPort
    POS only. Address of the machine running FishShopAdmin.exe.

.PARAMETER TerminalId
    POS only. Required non-blank (mirrors apps/pos/src/config.py's own
    validation, so the installer fails fast instead of shipping a .env that
    only errors at app launch).

.PARAMETER PrinterName / OnlineOrderUrl / PrinterEnabled / ReceiptCharsPerLine / ReceiptCut
    POS-only thermal receipt settings.
.PARAMETER StoreName / StorePhoneNumbers / StoreAddress / ReceiptPaperWidth
    POS only, optional (blank/default preserved if not supplied and already set).
#>

param(
    [Parameter(Mandatory = $true)][ValidateSet("Admin", "POS")][string]$Role,
    [string]$DatabaseUrl,
    [string]$AppPasswordFile,
    [string]$DbRole = "shop_admin",
    [string]$DbName = "shop_admin",
    [string]$DbHost = "localhost",
    [string]$DbPort = "5432",
    [string]$AdminLanPort = "8765",
    [string]$BusinessTimezone = "Asia/Yerevan",
    [string]$AdminHost = "127.0.0.1",
    [string]$AdminPort = "8765",
    [string]$TerminalId,
    [string]$PrinterName = "XP-80C",
    [string]$OnlineOrderUrl = "https://example.com/order",
    [string]$PrinterEnabled = "true",
    [ValidateRange(32, 48)][int]$ReceiptCharsPerLine = 48,
    [string]$ReceiptCut = "true",
    [string]$StoreName = "",
    [string]$StorePhoneNumbers = "",
    [string]$StoreAddress = "",
    [string]$ReceiptPaperWidth = "80"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

$TotalSteps = 4
$script:LogPath = Start-FishShopScriptLog -ScriptName "configure_environment"

try {
    $configDir = Get-FishShopConfigDir
    $dataDir = Get-FishShopDataDir
    $receiptsDir = Join-Path $dataDir "receipts"
    $envPath = Join-Path $configDir ".env"

    # [1/4] Ensure directories exist with correct ACLs
    Write-Step 1 $TotalSteps "Creating configuration/data directories..."
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    New-Item -ItemType Directory -Force -Path $receiptsDir | Out-Null
    # config\ holds DB credentials on Admin installs - restrict to Administrators/SYSTEM.
    & icacls $configDir /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" | Out-Null
    # data\ must be writable by any user running the POS app.
    & icacls $dataDir /inheritance:r /grant:r "*S-1-5-32-545:(OI)(CI)M" "*S-1-5-32-544:(OI)(CI)F" | Out-Null

    # [2/4] Determine install role
    Write-Step 2 $TotalSteps "Configuring for role: $Role"

    # [3/4] Compose desired key set for this role
    Write-Step 3 $TotalSteps "Composing configuration values..."
    $desired = [ordered]@{}
    if ($Role -eq "Admin") {
        if (-not $DatabaseUrl) {
            # Build the URL here rather than receiving it prebuilt: the
            # password must be percent-encoded to survive being embedded in a
            # URI (characters like @ : / # ? % would otherwise corrupt it),
            # and it must never be interpolated into a command line.
            if (-not $AppPasswordFile) {
                throw "-Role Admin requires either -DatabaseUrl or -AppPasswordFile."
            }
            if (-not (Test-Path $AppPasswordFile)) {
                throw "-AppPasswordFile '$AppPasswordFile' does not exist."
            }
            $appSecret = (Get-Content $AppPasswordFile -Raw) -replace '\r?\n$', ''
            if (-not $appSecret) {
                throw "-AppPasswordFile '$AppPasswordFile' is empty."
            }
            $encodedPassword = [uri]::EscapeDataString($appSecret)
            $encodedRole = [uri]::EscapeDataString($DbRole)
            $DatabaseUrl = "postgresql+psycopg://${encodedRole}:${encodedPassword}@${DbHost}:${DbPort}/${DbName}"
        }
        $desired["DATABASE_URL"] = $DatabaseUrl
        $desired["ADMIN_LAN_PORT"] = $AdminLanPort
        $desired["BUSINESS_TIMEZONE"] = $BusinessTimezone
    }
    else {
        if (-not $TerminalId) {
            throw "-TerminalId is required for -Role POS (mirrors POS_TERMINAL_ID validation in apps/pos/src/config.py)."
        }
        $desired["ADMIN_HOST"] = $AdminHost
        $desired["ADMIN_PORT"] = $AdminPort
        $desired["POS_TERMINAL_ID"] = $TerminalId
        $desired["PRINTER_NAME"] = if ($PrinterName) { $PrinterName } else { "XP-80C" }
        $desired["PRINTER_ENABLED"] = $PrinterEnabled
        $desired["RECEIPT_PAPER_WIDTH"] = $ReceiptPaperWidth
        $desired["RECEIPT_CHARS_PER_LINE"] = $ReceiptCharsPerLine
        $desired["RECEIPT_CUT"] = $ReceiptCut
        $desired["ONLINE_ORDER_URL"] = $OnlineOrderUrl
        $desired["STORE_NAME"] = $StoreName
        $desired["STORE_PHONE_NUMBERS"] = $StorePhoneNumbers
        $desired["STORE_ADDRESS"] = $StoreAddress
        $desired["RECEIPT_DIRECTORY"] = "receipts"
    }

    # [4/4] Merge into existing .env (upgrade-safe) and write
    Write-Step 4 $TotalSteps "Writing configuration (preserving unrelated existing values)..."
    $existing = Read-DotEnvFile -Path $envPath
    foreach ($key in $desired.Keys) {
        $existing[$key] = $desired[$key]
    }
    Write-DotEnvFile -Path $envPath -Values $existing
    & icacls $envPath /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null

    Write-Host "Configuration written to $envPath"
}
catch {
    Write-Error "Environment configuration failed: $($_.Exception.Message)"
    Write-Host "Full log saved to: $script:LogPath"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
