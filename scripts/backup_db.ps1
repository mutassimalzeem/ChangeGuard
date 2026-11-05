<#
.SYNOPSIS
    ChangeGuard - Automated Database Backup Script (PowerShell)
.DESCRIPTION
    Generates compressed, checksummed PostgreSQL backups with metadata manifests
    and automatic retention pruning.
.PARAMETER BackupDir
    Destination folder for database dumps. Defaults to ./backups.
.PARAMETER DatabaseUrl
    PostgreSQL connection string. Defaults to $env:DATABASE_URL.
.PARAMETER RetentionDays
    Retention period in days. Defaults to 7.
#>

param(
    [string]$BackupDir = "./backups",
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"

if (-not $DatabaseUrl) {
    $DatabaseUrl = "postgresql://postgres:postgres@localhost:5432/changeguard"
}

$cleanUrl = $DatabaseUrl -replace "postgresql\+asyncpg://", "postgresql://"

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
$backupFile = Join-Path $BackupDir "changeguard_backup_$timestamp.dump"
$checksumFile = "$backupFile.sha256"
$manifestFile = Join-Path $BackupDir "changeguard_backup_$timestamp.meta.json"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Starting ChangeGuard database backup..."
Write-Host "[$((Get-Date).ToString('u'))] [INFO] Target directory: $BackupDir"

# Execute pg_dump
try {
    & pg_dump --dbname=$cleanUrl --format=custom --compress=6 --no-owner --no-privileges --file=$backupFile
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }
}
catch {
    Write-Error "Backup failed: $_"
    if (Test-Path $backupFile) { Remove-Item $backupFile -Force }
    exit 1
}

$sizeBytes = (Get-Item $backupFile).Length
Write-Host "[$((Get-Date).ToString('u'))] [INFO] Dump completed. Size: $sizeBytes bytes"

# SHA256 checksum
$sha256 = (Get-FileHash -Path $backupFile -Algorithm SHA256).Hash.ToLower()
Set-Content -Path $checksumFile -Value "$sha256  $([System.IO.Path]::GetFileName($backupFile))"
Write-Host "[$((Get-Date).ToString('u'))] [INFO] SHA-256: $sha256"

# Manifest
$manifest = @{
    application = "ChangeGuard"
    version = "0.1.0"
    timestamp = $timestamp
    backup_file = [System.IO.Path]::GetFileName($backupFile)
    size_bytes = $sizeBytes
    sha256 = $sha256
    format = "pg_custom_archive"
    status = "completed"
} | ConvertTo-Json -Depth 4

Set-Content -Path $manifestFile -Value $manifest
Write-Host "[$((Get-Date).ToString('u'))] [INFO] Wrote metadata manifest: $manifestFile"

# Retention pruning
if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem -Path $BackupDir -Filter "changeguard_backup_*" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
    Write-Host "[$((Get-Date).ToString('u'))] [INFO] Retention pruning complete."
}

Write-Host "[$((Get-Date).ToString('u'))] [INFO] Backup successfully created: $backupFile"
exit 0
