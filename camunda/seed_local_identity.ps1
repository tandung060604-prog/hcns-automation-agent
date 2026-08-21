param(
    [string]$EngineRestUrl = "$(if ($env:CAMUNDA_REST_URL) { $env:CAMUNDA_REST_URL } else { 'http://127.0.0.1:8080/engine-rest' })",
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$Manifest = ".\config\camunda_local_identity.json",
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\seed_camunda_identity.py"
$resolvedPython = Join-Path $repoRoot $PythonPath
$resolvedManifest = Join-Path $repoRoot $Manifest
$healthUrl = "$($EngineRestUrl.TrimEnd('/'))/version"

if (-not (Test-Path -LiteralPath $resolvedPython)) {
    throw "Python executable not found: $resolvedPython"
}
if (-not (Test-Path -LiteralPath $resolvedManifest)) {
    throw "Identity manifest not found: $resolvedManifest"
}

$ready = $false
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    throw "Camunda REST did not become ready within $WaitSeconds seconds: $healthUrl"
}

$env:CAMUNDA_REST_URL = $EngineRestUrl
& $resolvedPython $scriptPath --engine-rest-url $EngineRestUrl --manifest $resolvedManifest
if ($LASTEXITCODE -ne 0) {
    throw "Camunda identity seeding failed with exit code $LASTEXITCODE"
}
