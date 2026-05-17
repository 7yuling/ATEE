[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$ProjectRoot = "",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Force) {
    throw "Restore overwrites config/data files. Re-run with -Force after stopping ATEE."
}

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $ProjectRoot = Join-Path $PSScriptRoot "..\.."
    } else {
        $ProjectRoot = "."
    }
}

if (-not (Test-Path $ProjectRoot)) {
    throw "ProjectRoot must point to an existing ATEE installation directory."
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$BackupPath = (Resolve-Path $BackupPath).Path
$restoreRoot = Join-Path ([System.IO.Path]::GetTempPath()) "atee-restore-$PID"

try {
    Expand-Archive -LiteralPath $BackupPath -DestinationPath $restoreRoot -Force

    $manifestPath = Join-Path $restoreRoot "manifest.json"
    if (-not (Test-Path $manifestPath)) {
        throw "Backup archive does not contain manifest.json."
    }

    $secretsPath = Join-Path $restoreRoot "config\secrets"
    if (Test-Path $secretsPath) {
        throw "Backup archive unexpectedly contains config/secrets; refusing to restore."
    }

    $configPath = Join-Path $restoreRoot "config\config.json"
    if (Test-Path $configPath) {
        New-Item -ItemType Directory -Path (Join-Path $ProjectRoot "config") -Force | Out-Null
        Copy-Item -LiteralPath $configPath -Destination (Join-Path $ProjectRoot "config\config.json") -Force
    }

    $dataRestoreDir = Join-Path $restoreRoot "data"
    if (Test-Path $dataRestoreDir) {
        New-Item -ItemType Directory -Path (Join-Path $ProjectRoot "data") -Force | Out-Null
        Get-ChildItem -LiteralPath $dataRestoreDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ProjectRoot "data\$($_.Name)") -Force
        }
    }

    Write-Output "Restored ATEE state from: $BackupPath"
} finally {
    Remove-Item -LiteralPath $restoreRoot -Recurse -Force -ErrorAction SilentlyContinue
}
