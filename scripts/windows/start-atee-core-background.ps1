[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8787,
    [string]$LogDir = "",
    [int]$WaitSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-LocalPort([string]$HostName, [int]$PortNumber, [int]$TimeoutMs) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

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
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    }
}
if (-not $LogDir) {
    $LogDir = Join-Path $ProjectRoot "logs"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$env:ATEE_HOST = $BindHost
$env:ATEE_PORT = [string]$Port
$env:PYTHONUNBUFFERED = "1"

# Some shells expose both Path and PATH. Even enumerating Env: can fail in
# that state, and Start-Process treats environment names case-insensitively.
# PythonExe has already been resolved above, so dropping PATH here is safe.
Remove-Item Env:PATH -ErrorAction SilentlyContinue

$preflightLog = Join-Path $LogDir "atee-preflight.log"
$stdoutLog = Join-Path $LogDir "atee-server.out.log"
$stderrLog = Join-Path $LogDir "atee-server.err.log"
$pidFile = Join-Path $LogDir "atee-server.pid"

Push-Location $ProjectRoot
try {
    & $PythonExe "services\core-service\check_config.py" *> $preflightLog
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $process = Start-Process `
        -WindowStyle Hidden `
        -FilePath $PythonExe `
        -ArgumentList "services\core-service\run_server.py" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    [string]$process.Id | Set-Content -LiteralPath $pidFile -Encoding ASCII

    $ready = $false
    for ($i = 0; $i -lt ($WaitSeconds * 2); $i++) {
        if (Test-LocalPort $BindHost $Port 500) {
            try {
                Invoke-WebRequest -UseBasicParsing "http://$BindHost`:$Port/health" -TimeoutSec 2 | Out-Null
                $ready = $true
                break
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
        Start-Sleep -Milliseconds 500
    }

    [pscustomobject]@{
        ok = $ready
        pid = $process.Id
        url = "http://$BindHost`:$Port/"
        preflight_log = $preflightLog
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        pid_file = $pidFile
    } | ConvertTo-Json

    if (-not $ready) {
        exit 1
    }
} finally {
    Pop-Location
}
