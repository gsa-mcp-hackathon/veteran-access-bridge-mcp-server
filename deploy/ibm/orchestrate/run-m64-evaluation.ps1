[CmdletBinding()]
param(
    [string]$EnvironmentName = "veteran-access-dev",
    [switch]$SkipAnalysis
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$testPath = Join-Path $repoRoot "eval\watsonx\m64_direct_tests"
$resultsRoot = Join-Path $repoRoot "eval\watsonx\m64_results"
$envFile = Join-Path $repoRoot "eval\watsonx\.env"
$expectedTestCount = 13

if (-not (Test-Path $testPath)) {
    throw "Missing direct M6.4 evaluation tests: $testPath"
}

$tests = Get-ChildItem $testPath -Filter "*.json" -File | Sort-Object Name
if ($tests.Count -ne $expectedTestCount) {
    throw "Expected $expectedTestCount direct M6.4 evaluation JSON files in $testPath but found $($tests.Count)."
}

Write-Host "Validating $expectedTestCount M6.4 JSON test files..."
foreach ($test in $tests) {
    try {
        Get-Content $test.FullName -Raw | ConvertFrom-Json | Out-Null
    }
    catch {
        throw "Invalid JSON in $($test.FullName): $($_.Exception.Message)"
    }
}

New-Item -ItemType Directory -Force $resultsRoot | Out-Null

Write-Host "Activating watsonx Orchestrate environment '$EnvironmentName'..."
orchestrate env activate $EnvironmentName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate watsonx Orchestrate environment '$EnvironmentName'."
}

Write-Host "Verifying M6.4 agent and identity-first toolkit..."
$toolkitText = (& orchestrate toolkits list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list Orchestrate toolkits."
}
if ($toolkitText -notmatch "veteran-access-mcp-remote-m64") {
    throw "Missing M6.4 toolkit veteran-access-mcp-remote-m64."
}
if ($toolkitText -notmatch "verify_synthetic_identity") {
    throw "M6.4 toolkit is stale: verify_synthetic_identity is not registered."
}

$agentText = (& orchestrate agents list 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list Orchestrate agents."
}
if ($agentText -notmatch "veteran_access_agent_m64") {
    throw "Missing M6.4 agent veteran_access_agent_m64."
}

$envArgs = @()
if (Test-Path $envFile) {
    $envArgs = @("--env-file", $envFile)
    Write-Host "Using local evaluation env file: $envFile"
}
else {
    Write-Host "No eval\watsonx\.env found; using the active Orchestrate/gateway configuration."
}

Write-Host "Running direct M6.4 evaluation against $expectedTestCount versioned test cases..."
$evaluateArgs = @(
    "evaluations", "evaluate",
    "--test-paths", $testPath,
    "--output-dir", $resultsRoot
) + $envArgs

& orchestrate @evaluateArgs
if ($LASTEXITCODE -ne 0) {
    throw "watsonx Orchestrate M6.4 evaluation failed."
}

$execution = Get-ChildItem $resultsRoot -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "summary_metrics.csv") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $execution) {
    throw "Evaluation completed but no execution directory with summary_metrics.csv was found."
}

$summaryPath = Join-Path $execution.FullName "summary_metrics.csv"

Write-Host ""
Write-Host "============================================================"
Write-Host "M6.4 EVALUATION SUMMARY (paste this block back into ChatGPT)"
Write-Host "============================================================"
Write-Host "Execution: $($execution.FullName)"
Write-Host "Test count: $expectedTestCount"
Write-Host "Summary file: $summaryPath"
Write-Host ""
Get-Content $summaryPath
Write-Host "============================================================"
Write-Host ""

if (-not $SkipAnalysis) {
    Write-Host "Running standard analysis (non-blocking post-processing)..."
    $analyzeArgs = @(
        "evaluations", "analyze",
        "-d", $execution.FullName
    ) + $envArgs

    & orchestrate @analyzeArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning (
            "Standard analysis failed after evaluation completed. " +
            "The evaluation results and summary_metrics.csv remain valid. " +
            "This can occur with IBM analyzer/text_match schema incompatibilities."
        )
    }

    Write-Host "Running enhanced analysis (non-blocking post-processing)..."
    $enhancedArgs = @(
        "evaluations", "analyze",
        "--mode", "enhanced",
        "-d", $execution.FullName
    ) + $envArgs

    & orchestrate @enhancedArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning (
            "Enhanced analysis failed after evaluation completed. " +
            "Use summary_metrics.csv and the execution artifacts for acceptance review."
        )
    }
}

Write-Host ""
Write-Host "M6.4 direct CLI evaluation workflow complete."
Write-Host "Test cases: $testPath"
Write-Host "Results:    $($execution.FullName)"
Write-Host "Summary:    $summaryPath"
