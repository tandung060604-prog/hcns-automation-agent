param(
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$HeldoutRoot = "",
    [string]$CccdHeldoutRoot = "",
    [string]$ExternalDatasetRoot = "",
    [string]$ExternalDatasetInventory = "",
    [string]$ExternalDatasetGroundTruth = "",
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
if ($CccdHeldoutRoot -and -not (Test-Path -LiteralPath $CccdHeldoutRoot)) {
    throw "CCCD held-out root not found: $CccdHeldoutRoot"
}
if ($ExternalDatasetRoot -and -not (Test-Path -LiteralPath $ExternalDatasetRoot)) {
    throw "External dataset root not found: $ExternalDatasetRoot"
}
if ($ExternalDatasetInventory -and -not (Test-Path -LiteralPath $ExternalDatasetInventory)) {
    throw "External dataset inventory not found: $ExternalDatasetInventory"
}
if ($ExternalDatasetGroundTruth -and -not (Test-Path -LiteralPath $ExternalDatasetGroundTruth)) {
    throw "External dataset Ground Truth draft not found: $ExternalDatasetGroundTruth"
}

$env:PYTHONPATH = Join-Path $repoRoot "src"
if ($ExternalDatasetRoot) {
    $env:VITE_SHOW_EXTERNAL_DATASET_REVIEW = "true"
}

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
    if ($CccdHeldoutRoot) {
        $apiArguments += @("--cccd-heldout-root", "`"$CccdHeldoutRoot`"")
    }
    if ($ExternalDatasetRoot) {
        $apiArguments += @("--external-dataset-root", "`"$ExternalDatasetRoot`"")
    }
    if ($ExternalDatasetInventory) {
        $apiArguments += @("--external-dataset-inventory", "`"$ExternalDatasetInventory`"")
    }
    if ($ExternalDatasetGroundTruth) {
        $apiArguments += @("--external-dataset-ground-truth", "`"$ExternalDatasetGroundTruth`"")
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
