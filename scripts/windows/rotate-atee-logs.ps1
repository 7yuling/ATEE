[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$LogDir = "",
    [int]$MaxBytes = 10485760,
    [int]$KeepFiles = 5
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
if (-not $LogDir) {
    $LogDir = Join-Path $ProjectRoot "logs"
}
if (-not (Test-Path $LogDir)) {
    Write-Output "Log directory does not exist: $LogDir"
    exit 0
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Get-ChildItem -LiteralPath $LogDir -Filter "*.log" -File | ForEach-Object {
    if ($_.Length -lt $MaxBytes) {
        return
    }
    $archiveName = "$($_.BaseName).$timestamp$($_.Extension)"
    Move-Item -LiteralPath $_.FullName -Destination (Join-Path $LogDir $archiveName) -Force
    New-Item -ItemType File -Path $_.FullName -Force | Out-Null

    $pattern = "$($_.BaseName).*$(($_.Extension))"
    $archives = Get-ChildItem -LiteralPath $LogDir -Filter $pattern -File |
        Sort-Object LastWriteTimeUtc -Descending
    $archives | Select-Object -Skip $KeepFiles | Remove-Item -Force
}

Write-Output "Log rotation completed for: $LogDir"
