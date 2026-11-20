[CmdletBinding()]
param(
    [string]$EnvironmentName = "veteran-access-dev"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$testPath = Join-Path $repoRoot "eval\watsonx\direct_tests"
$resultsRoot = Join-Path $repoRoot "eval\watsonx\results"
$envFile = Join-Path $repoRoot "eval\watsonx\.env"

if (-not (Test-Path $testPath)) {
    throw "Missing direct evaluation tests: $testPath"
}

$tests = Get-ChildItem $testPath -Filter "*.json" -File
if ($tests.Count -ne 10) {
    throw "Expected 10 direct M6.3 evaluation JSON files in $testPath but found $($tests.Count)."
}

New-Item -ItemType Directory -Force $resultsRoot | Out-Null

Write-Host "Activating watsonx Orchestrate environment '$EnvironmentName'..."
orchestrate env activate $EnvironmentName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate watsonx Orchestrate environment '$EnvironmentName'."
}

$envArgs = @()
if (Test-Path $envFile) {
    $envArgs = @("--env-file", $envFile)
    Write-Host "Using local evaluation env file: $envFile"
}
else {
    Write-Host "No eval\watsonx\.env found; using the active Orchestrate/gateway configuration."
}

Write-Host "Running direct M6.3 evaluation against 10 versioned test cases..."
$evaluateArgs = @(
    "evaluations", "evaluate",
    "--test-paths", $testPath,
    "--output-dir", $resultsRoot
) + $envArgs

& orchestrate @evaluateArgs
if ($LASTEXITCODE -ne 0) {
    throw "watsonx Orchestrate evaluation failed."
}

$execution = Get-ChildItem $resultsRoot -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "summary_metrics.csv") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $execution) {
    throw "Evaluation completed but no completed execution directory with summary_metrics.csv was found."
}

Write-Host "Evaluation execution: $($execution.FullName)"
Write-Host "Running standard analysis..."

$analyzeArgs = @(
    "evaluations", "analyze",
    "-d", $execution.FullName
) + $envArgs

& orchestrate @analyzeArgs
if ($LASTEXITCODE -ne 0) {
    throw "watsonx Orchestrate standard analysis failed."
}

Write-Host "Running enhanced analysis..."
$enhancedArgs = @(
    "evaluations", "analyze",
    "--mode", "enhanced",
    "-d", $execution.FullName
) + $envArgs

& orchestrate @enhancedArgs
if ($LASTEXITCODE -ne 0) {
    throw "watsonx Orchestrate enhanced analysis failed."
}

Write-Host ""
Write-Host "M6.3 direct CLI evaluation workflow complete."
Write-Host "Test cases: $testPath"
Write-Host "Results:    $($execution.FullName)"
