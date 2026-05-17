[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8787,
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
if (-not $PythonExe) {
    if (Test-Path "C:\Python314\python.exe") {
        $PythonExe = "C:\Python314\python.exe"
    } else {
        $PythonExe = "python"
    }
}
if (-not $LogDir) {
    $LogDir = Join-Path $ProjectRoot "logs"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Location $ProjectRoot

$env:ATEE_HOST = $BindHost
$env:ATEE_PORT = [string]$Port
$env:PYTHONUNBUFFERED = "1"

$preflightLog = Join-Path $LogDir "atee-preflight.log"
$stdoutLog = Join-Path $LogDir "atee-server.out.log"
$stderrLog = Join-Path $LogDir "atee-server.err.log"

& $PythonExe "services\core-service\check_config.py" *> $preflightLog
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $PythonExe "services\core-service\run_server.py" >> $stdoutLog 2>> $stderrLog
exit $LASTEXITCODE
