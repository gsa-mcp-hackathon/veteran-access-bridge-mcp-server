[CmdletBinding()]
param(
    [string]$EnvironmentName = "veteran-access-dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$agentFile = Join-Path $repoRoot "agents\veteran-access-agent.yaml"

if (-not (Test-Path $agentFile)) {
    throw "Agent definition not found: $agentFile"
}

Write-Host "Activating watsonx Orchestrate environment '$EnvironmentName'..."
orchestrate env activate $EnvironmentName
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate watsonx Orchestrate environment '$EnvironmentName'."
}

Write-Host "Importing updated veteran_access_agent draft..."
orchestrate agents import -f $agentFile
if ($LASTEXITCODE -ne 0) {
    throw "Failed to import updated veteran_access_agent."
}

Write-Host "Updated veteran_access_agent imported into the active Orchestrate environment."
