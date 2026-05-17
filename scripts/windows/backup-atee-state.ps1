[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$BackupDir = "",
    [switch]$IncludeLogs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $ProjectRoot = Join-Path $PSScriptRoot "..\.."
    } else {
        $ProjectRoot = "."
    }
}
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
if (-not $BackupDir) {
    $BackupDir = Join-Path $ProjectRoot "backups"
}
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archivePath = Join-Path $BackupDir "atee-state-$timestamp.zip"
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) "atee-backup-$timestamp-$PID"
$included = New-Object System.Collections.Generic.List[string]

try {
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

    $configPath = Join-Path $ProjectRoot "config\config.json"
    if (Test-Path $configPath) {
        New-Item -ItemType Directory -Path (Join-Path $stagingRoot "config") -Force | Out-Null
        Copy-Item -LiteralPath $configPath -Destination (Join-Path $stagingRoot "config\config.json") -Force
        $included.Add("config/config.json")
    }

    $dataDir = Join-Path $ProjectRoot "data"
    $sqliteFiles = @("atee_ledger.sqlite3", "atee_ledger.sqlite3-wal", "atee_ledger.sqlite3-shm")
    foreach ($fileName in $sqliteFiles) {
        $source = Join-Path $dataDir $fileName
        if (Test-Path $source) {
            New-Item -ItemType Directory -Path (Join-Path $stagingRoot "data") -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination (Join-Path $stagingRoot "data\$fileName") -Force
            $included.Add("data/$fileName")
        }
    }

    if ($IncludeLogs) {
        $logDir = Join-Path $ProjectRoot "logs"
        if (Test-Path $logDir) {
            $logs = Get-ChildItem -LiteralPath $logDir -Filter "*.log" -File -ErrorAction SilentlyContinue
            if ($logs) {
                New-Item -ItemType Directory -Path (Join-Path $stagingRoot "logs") -Force | Out-Null
                foreach ($log in $logs) {
                    Copy-Item -LiteralPath $log.FullName -Destination (Join-Path $stagingRoot "logs\$($log.Name)") -Force
                    $included.Add("logs/$($log.Name)")
                }
            }
        }
    }

    $manifest = [ordered]@{
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        project_root = $ProjectRoot
        included = @($included)
        excluded = @("config/secrets", "*.key", "*.secret", "node_modules", "runtime")
        note = "Secrets are intentionally excluded. Backups may contain runtime configuration and SQLite security summaries."
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stagingRoot "manifest.json") -Encoding UTF8

    Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $archivePath -Force
    Write-Output "Created backup: $archivePath"
} finally {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}
