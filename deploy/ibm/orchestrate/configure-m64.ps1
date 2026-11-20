<#
.SYNOPSIS
    Configure the isolated M6.4 Avery autonomous scheduling candidate in
    watsonx Orchestrate without modifying the validated M6.3 toolkit or agent.

.DESCRIPTION
    Creates/replaces only the M6.4 remote MCP toolkit and imports the separate
    veteran_access_agent_m64 draft candidate.

    The existing veteran_access_mcp_connection is reused. This script does not
    alter M6.3, does not deploy an agent version, and does not change Live
    credentials.

    If the existing Draft connection credential is stale, refresh it separately
    before running this script. By default this script is DRY-RUN only.
#>

param(
    [bool] $DryRun = $true,
    [string] $ToolkitName = "veteran-access-mcp-remote-m64",
    [string] $ConnectionId = "veteran_access_mcp_connection",
    [string] $McpUrl = "https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/mcp/"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command orchestrate -ErrorAction SilentlyContinue)) {
    throw "'orchestrate' was not found. Install or upgrade with: python -m pip install --upgrade ibm-watsonx-orchestrate"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$agentFile = Join-Path $repoRoot "agents\veteran-access-agent-m64.yaml"

if (-not (Test-Path $agentFile)) {
    throw "M6.4 agent definition not found: $agentFile"
}

function Invoke-OrchestrateStep {
    param(
        [string] $Label,
        [string[]] $Arguments
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    Write-Host "    orchestrate $($Arguments -join ' ')" -ForegroundColor Gray

    if (-not $DryRun) {
        & orchestrate @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "orchestrate command failed during: $Label"
        }
    }
}

Write-Host ""
Write-Host "Veteran Access Bridge - watsonx Orchestrate M6.4 Candidate" -ForegroundColor Yellow
Write-Host "  DryRun       : $DryRun"
Write-Host "  Toolkit      : $ToolkitName"
Write-Host "  Connection   : $ConnectionId"
Write-Host "  MCP URL      : $McpUrl"
Write-Host "  Agent        : veteran_access_agent_m64"
Write-Host "  Agent file   : $agentFile"
Write-Host "  M6.3 impact  : none"

if ($DryRun) {
    Write-Host "  [DRY RUN - no Orchestrate changes will execute]" -ForegroundColor Magenta
}

Invoke-OrchestrateStep "List environments" @("env", "list")
Invoke-OrchestrateStep "Inspect current connections" @("connections", "list")

Write-Host ""
Write-Host "==> Replace M6.4 toolkit if present" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "    orchestrate toolkits list"
    Write-Host "    orchestrate toolkits remove --name $ToolkitName  # only if M6.4 candidate already exists"
}
else {
    $toolkits = (& orchestrate toolkits list 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Unable to list Orchestrate toolkits." }
    if ($toolkits -match [regex]::Escape($ToolkitName)) {
        & orchestrate toolkits remove --name $ToolkitName
        if ($LASTEXITCODE -ne 0) { throw "Unable to remove existing toolkit $ToolkitName." }
    }
}

Invoke-OrchestrateStep "Register isolated M6.4 remote MCP toolkit" @(
    "toolkits", "add",
    "--kind", "mcp",
    "--name", $ToolkitName,
    "--description", "Veteran Access Bridge M6.4 autonomous scheduling candidate",
    "--url", $McpUrl,
    "--transport", "streamable_http",
    "--tools", "verify_synthetic_identity,get_scheduling_encounter,assess_access_standard,search_availability,determine_workflow_state,get_case_lifecycle_state,prepare_scheduling_handoff,get_scheduling_handoff,validate_option_selection,prepare_veteran_confirmation_request",
    "--app-id", $ConnectionId
)

Invoke-OrchestrateStep "Import isolated M6.4 Avery candidate" @(
    "agents", "import", "-f", $agentFile
)

Invoke-OrchestrateStep "Verify toolkits" @("toolkits", "list")
Invoke-OrchestrateStep "Verify agents" @("agents", "list")

Write-Host ""
Write-Host "M6.4 candidate configuration complete." -ForegroundColor Green
Write-Host "Validated M6.3 remains unchanged."
Write-Host "Next: run pwsh ./deploy/ibm/orchestrate/run-m64-evaluation.ps1. Do not deploy M6.4 Live yet."
