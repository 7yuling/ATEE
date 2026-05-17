[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$LogDir = ""
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

$pidFile = Join-Path $LogDir "atee-server.pid"
if (-not (Test-Path $pidFile)) {
    Write-Output "ATEE background pid file was not found: $pidFile"
    exit 0
}

$pidText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
if (-not $pidText) {
    Remove-Item -LiteralPath $pidFile -Force
    Write-Output "ATEE background pid file was empty and has been removed."
    exit 0
}

$process = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $process.Id -Force
    Write-Output "Stopped ATEE Core background process $($process.Id)."
} else {
    Write-Output "ATEE Core background process $pidText was not running."
}
Remove-Item -LiteralPath $pidFile -Force
