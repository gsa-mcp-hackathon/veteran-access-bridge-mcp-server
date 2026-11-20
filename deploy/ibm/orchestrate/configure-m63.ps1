<#
.SYNOPSIS
    Configure the M6.3 Veteran Access Bridge remote MCP toolkit and agent draft
    in watsonx Orchestrate.

.DESCRIPTION
    Reuses the existing veteran_access_mcp_connection connection, updates its
    Draft bearer credential from VAB_MCP_API_KEY, replaces the M6.3 remote MCP
    toolkit if it already exists, and imports the checked-in veteran_access_agent.

    This script does not create a second agent and does not deploy an agent
    version. Run the canonical acceptance prompt in Draft Preview first.

    By default this script is DRY-RUN only. Set -DryRun $false to execute.
#>

param(
    [bool] $DryRun = $true,
    [string] $ToolkitName = "veteran-access-mcp-remote-m63",
    [string] $ConnectionId = "veteran_access_mcp_connection",
    [string] $McpUrl = "https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/mcp/",
    [switch] $SetLiveCredentials
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command orchestrate -ErrorAction SilentlyContinue)) {
    throw "'orchestrate' was not found. Install or upgrade with: python -m pip install --upgrade ibm-watsonx-orchestrate"
}

if ([string]::IsNullOrWhiteSpace($env:VAB_MCP_API_KEY)) {
    throw "VAB_MCP_API_KEY is required in the current process environment."
}

$McpApiKey = $env:VAB_MCP_API_KEY.Trim()
if ($McpApiKey -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "VAB_MCP_API_KEY must be the 64-character hex bearer credential."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$agentFile = Join-Path $repoRoot "agents\veteran-access-agent.yaml"

if (-not (Test-Path $agentFile)) {
    throw "Agent definition not found: $agentFile"
}

function Invoke-OrchestrateStep {
    param(
        [string] $Label,
        [string[]] $Arguments,
        [switch] $Sensitive
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    if ($Sensitive) {
        Write-Host "    orchestrate <credential command redacted>" -ForegroundColor Gray
    }
    else {
        Write-Host "    orchestrate $($Arguments -join ' ')" -ForegroundColor Gray
    }

    if (-not $DryRun) {
        & orchestrate @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "orchestrate command failed during: $Label"
        }
    }
}

Write-Host ""
Write-Host "Veteran Access Bridge - watsonx Orchestrate M6.3 Closeout" -ForegroundColor Yellow
Write-Host "  DryRun       : $DryRun"
Write-Host "  Toolkit      : $ToolkitName"
Write-Host "  Connection   : $ConnectionId"
Write-Host "  MCP URL      : $McpUrl"
Write-Host "  Agent        : veteran_access_agent"
Write-Host "  Agent file   : $agentFile"
Write-Host "  Live creds   : $SetLiveCredentials"

if ($DryRun) {
    Write-Host "  [DRY RUN - no Orchestrate changes will execute]" -ForegroundColor Magenta
}

Invoke-OrchestrateStep "List environments" @("env", "list")
Invoke-OrchestrateStep "Inspect current connections" @("connections", "list")
Invoke-OrchestrateStep "Set Draft bearer credential" @("connections", "set-credentials", "-a", $ConnectionId, "--env", "draft", "--token", $McpApiKey) -Sensitive

if ($SetLiveCredentials) {
    Invoke-OrchestrateStep "Set Live bearer credential" @("connections", "set-credentials", "-a", $ConnectionId, "--env", "live", "--token", $McpApiKey) -Sensitive
}

Write-Host ""
Write-Host "==> Replace M6.3 toolkit if present" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "    orchestrate toolkits list"
    Write-Host "    orchestrate toolkits remove --name $ToolkitName  # only if present"
}
else {
    $toolkits = (& orchestrate toolkits list 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Unable to list Orchestrate toolkits." }
    if ($toolkits -match [regex]::Escape($ToolkitName)) {
        & orchestrate toolkits remove --name $ToolkitName
        if ($LASTEXITCODE -ne 0) { throw "Unable to remove existing toolkit $ToolkitName." }
    }
}

Invoke-OrchestrateStep "Register M6.3 remote MCP toolkit" @("toolkits", "add", "--kind", "mcp", "--name", $ToolkitName, "--description", "Veteran Access Bridge governed remote MCP on IBM Code Engine", "--url", $McpUrl, "--transport", "streamable_http", "--tools", "get_scheduling_encounter,assess_access_standard,search_availability,determine_workflow_state", "--app-id", $ConnectionId)
Invoke-OrchestrateStep "Import existing Veteran Access Agent" @("agents", "import", "-f", $agentFile)
Invoke-OrchestrateStep "Verify connections" @("connections", "list")
Invoke-OrchestrateStep "Verify toolkits" @("toolkits", "list")

Write-Host ""
Write-Host "M6.3 Orchestrate draft configuration complete." -ForegroundColor Green
Write-Host "Next: open veteran_access_agent Draft Preview and run the canonical M6.3 acceptance prompt."
Write-Host "Do not deploy a version until Draft Preview acceptance passes."
