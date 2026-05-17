[CmdletBinding()]
param(
    [string]$TaskName = "ATEE Core Service",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "",
    [ValidateSet("AtLogOn", "AtStartup")]
    [string]$Trigger = "AtLogOn",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8787,
    [string]$LogDir = "",
    [switch]$NoStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Quote-Arg([string]$Value) {
    '"' + ($Value -replace '"', '\"') + '"'
}

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $ProjectRoot = Join-Path $PSScriptRoot "..\.."
    } else {
        $ProjectRoot = "."
    }
}
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$StartScript = Join-Path $ProjectRoot "scripts\windows\start-atee-core.ps1"
if (-not (Test-Path $StartScript)) {
    throw "start-atee-core.ps1 was not found under $ProjectRoot"
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-Arg $StartScript),
    "-ProjectRoot", (Quote-Arg $ProjectRoot),
    "-BindHost", (Quote-Arg $BindHost),
    "-Port", [string]$Port
)
if ($PythonExe) {
    $arguments += @("-PythonExe", (Quote-Arg $PythonExe))
}
if ($LogDir) {
    $arguments += @("-LogDir", (Quote-Arg $LogDir))
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($arguments -join " ") `
    -WorkingDirectory $ProjectRoot

if ($Trigger -eq "AtStartup") {
    $taskTrigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $taskTrigger `
    -Settings $settings `
    -Description "Runs ATEE Core Service with config preflight and local log files." | Out-Null

if (-not $NoStart) {
    Start-ScheduledTask -TaskName $TaskName
}

Write-Output "Installed scheduled task '$TaskName'. Trigger=$Trigger Host=$BindHost Port=$Port"
