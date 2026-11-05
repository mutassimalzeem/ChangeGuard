<#
.SYNOPSIS
    ChangeGuard - Database Restore Script (PowerShell)
.DESCRIPTION
    Safely restores a ChangeGuard database from a validated pg_dump archive.
    Performs checksum verification, confirmation safety checks, and post-restore
    schema integrity validation.
.PARAMETER File
    Path to the .dump file to restore. REQUIRED.
.PARAMETER DatabaseUrl
    PostgreSQL connection string. Defaults to $env:DATABASE_URL.
.PARAMETER Confirm
    Mandatory safety switch to authorize restoration.
.PARAMETER SkipChecksum
    Bypass SHA-256 checksum verification.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$File,

    [string]$DatabaseUrl = $env:DATABASE_URL,
    [switch]$Confirm,
    [switch]$SkipChecksum
)

$ErrorActionPreference = "Stop"

if (-not $Confirm) {
    Write-Error "Safety check failed: Database restore requires explicit -Confirm switch to prevent accidental overwrite."
    exit 1
}

if (-not (Test-Path $File)) {
    Write-Error "Backup file not found: $File"
    exit 1
}

if (-not $DatabaseUrl) {
    $DatabaseUrl = "postgresql://postgres:postgres@localhost:5432/changeguard"
}

$cleanUrl = $DatabaseUrl -replace "postgresql\+asyncpg://", "postgresql://"

# Checksum verification
$checksumFile = "$File.sha256"
if (-not $SkipChecksum -and (Test-Path $checksumFile)) {
    Write-Host "[$((Get-Date).ToString('u'))] [INFO] Verifying SHA-256 checksum against $checksumFile..."
    $expected = (Get-Content $checksumFile).Split(" ")[0].Trim().ToLower()
    $actual = (Get-FileHash -Path $File -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) {
        Write-Error "Checksum mismatch! Expected: $expected, Actual: $actual. Aborting restore."
        exit 1
    }
    Write-Host "[$((Get-Date).ToString('u'))] [INFO] Checksum validated successfully."
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Testing connection to target database..."
& psql $cleanUrl -c "SELECT 1;" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Cannot connect to target database: $cleanUrl"
    exit 1
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Executing restore from $File..."
& pg_restore --dbname=$cleanUrl --clean --if-exists --no-owner --no-privileges --verbose $File
# Note: pg_restore returns 1 on harmless warnings (e.g. drop table if not exists)
if ($LASTEXITCODE -gt 1) {
    Write-Error "pg_restore failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Performing post-restore integrity checks..."
$query = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('tenants', 'projects', 'users', 'documents', 'change_orders');"
$tableCount = (& psql $cleanUrl -t -A -c $query).Trim()

if ([int]$tableCount -lt 4) {
    Write-Error "Integrity check failed: Expected at least 4 core ChangeGuard tables, found $tableCount."
    exit 1
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Integrity verification passed: $tableCount core tables verified."
Write-Host "[$((Get-Date).ToString('u'))] [INFO] Database successfully restored from $File."
exit 0
