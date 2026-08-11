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
    [string]$ExternalDatasetPredictions = "",
    [string]$ExternalDatasetTypedProjection = "",
    [string]$ExternalDatasetTypedApproval = "",
    [string]$ExternalDatasetTypedReport = "",
    [string]$ExternalDatasetPolicyV2Report = "",
    [string]$ExternalDatasetPolicyV2Marker = "",
    [string]$M5LocalShadowReport = "",
    [string]$M5Cam006SmokeReport = "",
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
if ($ExternalDatasetPredictions -and -not (Test-Path -LiteralPath $ExternalDatasetPredictions)) {
    throw "External dataset predictions not found: $ExternalDatasetPredictions"
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
if ($ExternalDatasetPolicyV2Report -and -not (Test-Path -LiteralPath $ExternalDatasetPolicyV2Report)) {
    throw "External dataset policy v2 report not found: $ExternalDatasetPolicyV2Report"
}
if ($ExternalDatasetPolicyV2Marker -and -not (Test-Path -LiteralPath $ExternalDatasetPolicyV2Marker)) {
    throw "External dataset policy v2 marker not found: $ExternalDatasetPolicyV2Marker"
}
if ($M5LocalShadowReport -and -not (Test-Path -LiteralPath $M5LocalShadowReport)) {
    throw "M5 local shadow report not found: $M5LocalShadowReport"
}
if ($M5Cam006SmokeReport -and -not (Test-Path -LiteralPath $M5Cam006SmokeReport)) {
    throw "M5-CAM-006 smoke report not found: $M5Cam006SmokeReport"
}

$env:PYTHONPATH = Join-Path $repoRoot "src"

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
if ($apiRunning -and $OcrHoShadowRoot) {
    $expectedShadowRoot = (Resolve-Path -LiteralPath $OcrHoShadowRoot).Path
    $commandLine = [string]$apiProcess.CommandLine
    if ($commandLine.IndexOf($expectedShadowRoot, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Stop-Process -Id $apiProcess.ProcessId -Force
        Start-Sleep -Milliseconds 500
        $apiRunning = $false
    }
}
if ($apiRunning -and ($BenchmarkReport -or $ExternalDatasetPolicyV2Report -or $ExternalDatasetPolicyV2Marker -or $M5LocalShadowReport -or $M5Cam006SmokeReport)) {
    $commandLine = [string]$apiProcess.CommandLine
    $configuredPathsPresent = $true
    foreach ($configuredPath in @($BenchmarkReport, $ExternalDatasetPolicyV2Report, $ExternalDatasetPolicyV2Marker, $M5LocalShadowReport, $M5Cam006SmokeReport)) {
        if ($configuredPath -and $commandLine.IndexOf((Resolve-Path -LiteralPath $configuredPath).Path, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            $configuredPathsPresent = $false
        }
    }
    if (-not $configuredPathsPresent) {
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
    if ($ExternalDatasetPredictions) {
        $apiArguments += " --external-dataset-predictions `"$ExternalDatasetPredictions`""
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
    if ($ExternalDatasetPolicyV2Report) {
        $apiArguments += " --external-dataset-policy-v2-report `"$ExternalDatasetPolicyV2Report`""
    }
    if ($ExternalDatasetPolicyV2Marker) {
        $apiArguments += " --external-dataset-policy-v2-marker `"$ExternalDatasetPolicyV2Marker`""
    }
    if ($M5LocalShadowReport) {
        $apiArguments += " --m5-local-shadow-report `"$M5LocalShadowReport`""
    }
    if ($M5Cam006SmokeReport) {
        $apiArguments += " --m5-cam-006-smoke-report `"$M5Cam006SmokeReport`""
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
