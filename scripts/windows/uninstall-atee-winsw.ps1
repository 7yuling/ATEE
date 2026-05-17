[CmdletBinding()]
param(
    [string]$ServiceName = "ATEECore",
    [string]$ProjectRoot = "",
    [string]$InstallDir = "",
    [switch]$RemoveFiles
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
if (-not $InstallDir) {
    $InstallDir = Join-Path $ProjectRoot "runtime\winsw"
}

$WrapperExe = Join-Path $InstallDir "$ServiceName.exe"
if (-not (Test-Path $WrapperExe)) {
    Write-Output "WinSW wrapper '$WrapperExe' was not found."
    exit 0
}

& $WrapperExe stop
& $WrapperExe uninstall
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($RemoveFiles) {
    Remove-Item -LiteralPath $WrapperExe -Force
    $WrapperXml = Join-Path $InstallDir "$ServiceName.xml"
    if (Test-Path $WrapperXml) {
        Remove-Item -LiteralPath $WrapperXml -Force
    }
}

Write-Output "Uninstalled WinSW service '$ServiceName'."
