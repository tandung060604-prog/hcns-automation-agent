param(
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$CccdHeldoutRoot = "",
    [string]$BenchmarkReport = "",
    [string]$BenchmarkManifest = "",
    [string]$OcrHoShadowRoot = "",
    [string]$ExternalDatasetRoot = "",
    [string]$ExternalDatasetInventory = "",
    [string]$ExternalDatasetGroundTruth = "",
    [string]$ExternalDatasetTypedProjection = "",
    [string]$ExternalDatasetTypedApproval = "",
    [string]$ExternalDatasetTypedReport = "",
    [string]$ExternalDatasetPredictions = "",
    [string]$ExternalDatasetPredictionReport = "",
    [string]$ExternalDatasetPredictionMarker = "",
    [string]$PythonPath = "D:\venv_paddle\Scripts\python.exe",
    [ValidateSet("paddle", "easyocr")]
    [string]$TemplateOcrBackend = "paddle"
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
if ($CccdHeldoutRoot -and -not (Test-Path -LiteralPath $CccdHeldoutRoot)) {
    throw "CCCD held-out root not found: $CccdHeldoutRoot"
}
if ($BenchmarkReport -and -not (Test-Path -LiteralPath $BenchmarkReport)) {
    throw "Benchmark report not found: $BenchmarkReport"
}
if ($BenchmarkManifest -and -not (Test-Path -LiteralPath $BenchmarkManifest)) {
    throw "Benchmark manifest not found: $BenchmarkManifest"
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
if ($ExternalDatasetTypedProjection -and -not (Test-Path -LiteralPath $ExternalDatasetTypedProjection)) {
    throw "External dataset typed projection not found: $ExternalDatasetTypedProjection"
}
if ($ExternalDatasetTypedApproval -and -not (Test-Path -LiteralPath $ExternalDatasetTypedApproval)) {
    throw "External dataset typed approval not found: $ExternalDatasetTypedApproval"
}
if ($ExternalDatasetTypedReport -and -not (Test-Path -LiteralPath $ExternalDatasetTypedReport)) {
    throw "External dataset typed report not found: $ExternalDatasetTypedReport"
}
if ($ExternalDatasetPredictions -and -not (Test-Path -LiteralPath $ExternalDatasetPredictions)) {
    throw "External dataset predictions not found: $ExternalDatasetPredictions"
}
if ($ExternalDatasetPredictionReport -and -not (Test-Path -LiteralPath $ExternalDatasetPredictionReport)) {
    throw "External dataset prediction report not found: $ExternalDatasetPredictionReport"
}
if ($ExternalDatasetPredictionMarker -and -not (Test-Path -LiteralPath $ExternalDatasetPredictionMarker)) {
    throw "External dataset prediction marker not found: $ExternalDatasetPredictionMarker"
}

$env:PYTHONPATH = Join-Path $repoRoot "src"
$env:HCNS_TEMPLATE_OCR_BACKEND = $TemplateOcrBackend

function Get-ApiListener {
    $connection = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)"
}

function Wait-ApiHealth {
    param([bool]$RequireOcrHo)

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            Invoke-RestMethod "http://127.0.0.1:8765/health" -TimeoutSec 2 | Out-Null
            if (-not $RequireOcrHo) {
                return
            }
            $summary = Invoke-RestMethod "http://127.0.0.1:8765/ocr-ho-v2/diagnostic/summary" -TimeoutSec 2
            if ([int]$summary.documentCount -gt 0) {
                return $summary
            }
        } catch {
            # API may still be starting; retry before failing the launch.
        }
        Start-Sleep -Milliseconds 500
    }
    if ($RequireOcrHo) {
        throw "OCR-HO diagnostic API is empty or points to the wrong private root. Check -OcrHoShadowRoot."
    }
    throw "Local API did not become healthy on port 8765."
}

$apiProcess = Get-ApiListener
$apiRunning = $null -ne $apiProcess
if ($apiRunning) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:8765/health" -TimeoutSec 2
        $runtimeReady = [bool]$health.userUpload.paddleOcrAvailable
        $backendMatches = [string]$health.userUpload.templateOcrBackend -eq $TemplateOcrBackend
        if (-not $runtimeReady -or -not $backendMatches) {
            Stop-Process -Id $apiProcess.ProcessId -Force
            Start-Sleep -Milliseconds 500
            $apiRunning = $false
        }
    } catch {
        Stop-Process -Id $apiProcess.ProcessId -Force
        Start-Sleep -Milliseconds 500
        $apiRunning = $false
    }
}
if ($apiRunning -and $OcrHoShadowRoot) {
    $expectedShadowRoot = (Resolve-Path -LiteralPath $OcrHoShadowRoot).Path
    $commandLine = [string]$apiProcess.CommandLine
    if ($commandLine.IndexOf($expectedShadowRoot, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Stop-Process -Id $apiProcess.ProcessId -Force
        Start-Sleep -Milliseconds 500
        $apiRunning = $false
    }
}
if ($apiRunning -and $BenchmarkReport) {
    $expectedBenchmarkReport = (Resolve-Path -LiteralPath $BenchmarkReport).Path
    $commandLine = [string]$apiProcess.CommandLine
    if ($commandLine.IndexOf($expectedBenchmarkReport, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Stop-Process -Id $apiProcess.ProcessId -Force
        Start-Sleep -Milliseconds 500
        $apiRunning = $false
    }
}
if ($apiRunning -and $ExternalDatasetPredictions) {
    $expectedPredictions = (Resolve-Path -LiteralPath $ExternalDatasetPredictions).Path
    if ([string]$apiProcess.CommandLine -notlike "*$expectedPredictions*") {
        Stop-Process -Id $apiProcess.ProcessId -Force
        Start-Sleep -Milliseconds 500
        $apiRunning = $false
    }
}

if (-not $apiRunning) {
    $apiArguments = "-u `"$apiScript`" --data-root `"$DataRoot`" --host 127.0.0.1 --port 8765"
    if ($CccdHeldoutRoot) {
        $apiArguments += " --cccd-heldout-root `"$CccdHeldoutRoot`""
    }
    if ($BenchmarkReport) {
        $apiArguments += " --benchmark-report `"$BenchmarkReport`""
    }
    if ($BenchmarkManifest) {
        $apiArguments += " --benchmark-manifest `"$BenchmarkManifest`""
    }
    if ($OcrHoShadowRoot) {
        $apiArguments += " --ocr-ho-shadow-root `"$OcrHoShadowRoot`""
    }
    if ($ExternalDatasetRoot) {
        $apiArguments += " --external-dataset-root `"$ExternalDatasetRoot`""
    }
    if ($ExternalDatasetInventory) {
        $apiArguments += " --external-dataset-inventory `"$ExternalDatasetInventory`""
    }
    if ($ExternalDatasetGroundTruth) {
        $apiArguments += " --external-dataset-ground-truth `"$ExternalDatasetGroundTruth`""
    }
    if ($ExternalDatasetTypedProjection) {
        $apiArguments += " --external-dataset-typed-projection `"$ExternalDatasetTypedProjection`""
    }
    if ($ExternalDatasetTypedApproval) {
        $apiArguments += " --external-dataset-typed-approval `"$ExternalDatasetTypedApproval`""
    }
    if ($ExternalDatasetTypedReport) {
        $apiArguments += " --external-dataset-typed-report `"$ExternalDatasetTypedReport`""
    }
    if ($ExternalDatasetPredictions) {
        $apiArguments += " --external-dataset-predictions `"$ExternalDatasetPredictions`""
    }
    if ($ExternalDatasetPredictionReport) {
        $apiArguments += " --external-dataset-prediction-report `"$ExternalDatasetPredictionReport`""
    }
    if ($ExternalDatasetPredictionMarker) {
        $apiArguments += " --external-dataset-prediction-marker `"$ExternalDatasetPredictionMarker`""
    }
    Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $apiArguments `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden | Out-Null
}

Wait-ApiHealth -RequireOcrHo ($OcrHoShadowRoot -ne "") | Out-Null

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
