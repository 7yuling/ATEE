[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WinswExePath,
    [string]$ServiceName = "ATEECore",
    [string]$DisplayName = "ATEE Core Service",
    [string]$Description = "Runs ATEE Core Service with config preflight and local log files.",
    [string]$ProjectRoot = "",
    [string]$InstallDir = "",
    [string]$PythonExe = "",
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

function Xml-Escape([string]$Value) {
    [System.Security.SecurityElement]::Escape($Value)
}

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $ProjectRoot = Join-Path $PSScriptRoot "..\.."
    } else {
        $ProjectRoot = "."
    }
}
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$WinswExePath = (Resolve-Path $WinswExePath).Path
if (-not $InstallDir) {
    $InstallDir = Join-Path $ProjectRoot "runtime\winsw"
}
if (-not $LogDir) {
    $LogDir = Join-Path $ProjectRoot "logs"
}

$StartScript = Join-Path $ProjectRoot "scripts\windows\start-atee-core.ps1"
if (-not (Test-Path $StartScript)) {
    throw "start-atee-core.ps1 was not found under $ProjectRoot"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$WrapperExe = Join-Path $InstallDir "$ServiceName.exe"
$WrapperXml = Join-Path $InstallDir "$ServiceName.xml"
Copy-Item -LiteralPath $WinswExePath -Destination $WrapperExe -Force

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-Arg $StartScript),
    "-ProjectRoot", (Quote-Arg $ProjectRoot),
    "-BindHost", (Quote-Arg $BindHost),
    "-Port", [string]$Port,
    "-LogDir", (Quote-Arg $LogDir)
)
if ($PythonExe) {
    $arguments += @("-PythonExe", (Quote-Arg $PythonExe))
}

$ArgumentText = $arguments -join " "
$xml = @"
<service>
  <id>$(Xml-Escape $ServiceName)</id>
  <name>$(Xml-Escape $DisplayName)</name>
  <description>$(Xml-Escape $Description)</description>
  <executable>powershell.exe</executable>
  <arguments>$(Xml-Escape $ArgumentText)</arguments>
  <workingdirectory>$(Xml-Escape $ProjectRoot)</workingdirectory>
  <startmode>Automatic</startmode>
  <stoptimeout>30 sec</stoptimeout>
  <logpath>$(Xml-Escape $LogDir)</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10485760</sizeThreshold>
    <keepFiles>5</keepFiles>
  </log>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
</service>
"@
$xml | Set-Content -LiteralPath $WrapperXml -Encoding UTF8

& $WrapperExe install
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not $NoStart) {
    & $WrapperExe start
    exit $LASTEXITCODE
}

Write-Output "Installed WinSW service '$ServiceName'. Wrapper=$WrapperExe"
