param(
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$HeldoutRoot = "",
    [string]$PythonPath = "D:\venv_paddle\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$labRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $labRoot)
$dashboardRoot = Join-Path $labRoot "web"
$apiScript = Join-Path $PSScriptRoot "serve_dashboard_api.py"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python executable not found: $PythonPath"
}
if (-not (Test-Path -LiteralPath $DataRoot)) {
    throw "Data root not found: $DataRoot"
}
if ($HeldoutRoot -and -not (Test-Path -LiteralPath $HeldoutRoot)) {
    throw "Held-out root not found: $HeldoutRoot"
}

$env:PYTHONPATH = Join-Path $repoRoot "src"

$apiRunning = [bool](Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if (-not $apiRunning) {
    $apiArguments = @(
        "-u",
        "`"$apiScript`"",
        "--data-root",
        "`"$DataRoot`"",
        "--host",
        "127.0.0.1",
        "--port",
        "8765"
    )
    if ($HeldoutRoot) {
        $apiArguments += @("--heldout-root", "`"$HeldoutRoot`"")
    }
    Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $apiArguments `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden | Out-Null
}

$dashboardRunning = [bool](Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
if (-not $dashboardRunning) {
    $env:WRANGLER_LOG_PATH = ".wrangler/wrangler.log"
    Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $dashboardRoot `
        -WindowStyle Hidden | Out-Null
}

Write-Output "Dashboard: http://localhost:3000"
Write-Output "Local API: http://127.0.0.1:8765"
