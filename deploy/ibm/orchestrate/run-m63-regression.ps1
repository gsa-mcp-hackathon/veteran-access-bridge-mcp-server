[CmdletBinding()]
param(
    [string]$EnvironmentName = "veteran-access-dev"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$testPath = Join-Path $repoRoot "eval\watsonx\regression_tests"
$resultsRoot = Join-Path $repoRoot "eval\watsonx\results"
$envFile = Join-Path $repoRoot "eval\watsonx\.env"

$tests = Get-ChildItem $testPath -Filter "*.json" -File
if ($tests.Count -ne 6) {
    throw "Expected 6 focused regression tests in $testPath but found $($tests.Count)."
}

orchestrate env activate $EnvironmentName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate watsonx Orchestrate environment '$EnvironmentName'."
}

$envArgs = @()
if (Test-Path $envFile) {
    $envArgs = @("--env-file", $envFile)
}

Write-Host "Running focused M6.3 regression suite (01, 02, 05, 08, 09, 10)..."
$evaluateArgs = @(
    "evaluations", "evaluate",
    "--test-paths", $testPath,
    "--output-dir", $resultsRoot
) + $envArgs

& orchestrate @evaluateArgs
if ($LASTEXITCODE -ne 0) {
    throw "Focused M6.3 regression evaluation failed."
}

$execution = Get-ChildItem $resultsRoot -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "summary_metrics.csv") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $execution) {
    throw "No completed regression execution with summary_metrics.csv was found."
}

Write-Host "Focused regression complete."
Write-Host "Results: $($execution.FullName)"
Write-Host "Review with:"
Write-Host "Import-Csv '$($execution.FullName)\summary_metrics.csv' | Format-List *"
