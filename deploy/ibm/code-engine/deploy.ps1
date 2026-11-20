<#
.SYNOPSIS
    Veteran Access Bridge - validated IBM Cloud Code Engine redeploy helper.

.DESCRIPTION
    Updates the existing Veteran Access Bridge Code Engine application to a
    published private GHCR image.

    By default this script is DRY-RUN only. Set -DryRun $false to execute.

    Validated deployment:
      Region         : ca-tor
      Resource group : eid-6ac41f127818aff458d82ac8
      CE project     : ce-550000w6t0
      Application    : veteran-access-bridge
      Registry secret: ghcr-veteran-access
      MCP secret     : veteran-access-mcp-key
      Image          : ghcr.io/wbgreen0405/veteran-access-bridge:0.4.1

    The GHCR image is published by .github/workflows/publish-container.yml.
    This script does not build or push the container.

.PARAMETER DryRun
    When $true (default), print commands without executing.

.PARAMETER Version
    GHCR image version or immutable commit tag. Prefer sha-<full-git-sha>.
    Default: latest.

.PARAMETER Project
    Existing Code Engine project. Default: ce-550000w6t0.

.PARAMETER ResourceGroup
    IBM Cloud resource group. Default: eid-6ac41f127818aff458d82ac8.

.PARAMETER Region
    IBM Cloud region. Default: ca-tor.

.EXAMPLE
    .\deploy.ps1

.EXAMPLE
    .\deploy.ps1 -DryRun $false
#>

param(
    [bool]   $DryRun         = $true,
    [string] $Version        = "latest",
    [string] $Project        = "ce-550000w6t0",
    [string] $ResourceGroup  = "eid-6ac41f127818aff458d82ac8",
    [string] $Region         = "ca-tor",
    [string] $AppName        = "veteran-access-bridge",
    [string] $RegistrySecret        = "ghcr-veteran-access",
    [string] $McpSecretName         = "veteran-access-mcp-key",
    [string] $OrchestrateSecretName = "veteran-access-orchestrate-auth",
    [string] $EmbedSecretName       = "veteran-access-orchestrate-embed",
    [string] $IbmPhoneSecretName    = "",
    [string] $OrchestrateBaseUrl    = "",
    [string] $OrchestrateTenantId   = "194b6edd-bf14-4b92-b44a-751d836e022e",
    [string] $OrchestrateAgentId    = "89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3",
    [string] $OrchestrateChatPath   = "/v1/orchestrate/{agent_id}/chat/completions",
    [string] $AllowedUiOrigins      = "",
    [string] $IbmPhoneProvider      = "UNCONFIGURED",
    [bool]   $IbmPhoneConfigured    = $false,
    [string] $WebRtcGateway        = "UNCONFIGURED",
    [bool]   $WebRtcGatewayConfigured = $false,
    [string] $WebRtcSignalingUrl    = "",
    [bool]   $WebRtcSoftphone       = $false,
    [int]    $MinScale              = 1,
    [int]    $MaxScale              = 1,
    [string] $AppEnv                = "code-engine"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ImageRef = "ghcr.io/wbgreen0405/veteran-access-bridge:$Version"

function Invoke-Step {
    param([string]$Label, [string]$Cmd)

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    Write-Host "    $Cmd" -ForegroundColor Gray

    if (-not $DryRun) {
        Invoke-Expression $Cmd
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed: $Cmd"
        }
    }
}

Write-Host ""
Write-Host "Veteran Access Bridge - Code Engine Redeploy" -ForegroundColor Yellow
Write-Host "  DryRun        : $DryRun"
Write-Host "  Image         : $ImageRef"
if ($Version -eq "latest" -or $Version -eq "0.4.1") {
    Write-Warning "Mutable image tag '$Version' selected. Prefer an immutable sha-<full-git-sha> tag for reproducible deployment."
}
Write-Host "  Region        : $Region"
Write-Host "  ResourceGroup : $ResourceGroup"
Write-Host "  Project       : $Project"
Write-Host "  Application   : $AppName"
Write-Host "  AppEnv        : $AppEnv"
Write-Host "  Orchestrate   : remote"
Write-Host "  Tenant ID     : $OrchestrateTenantId"
Write-Host "  Agent ID      : $OrchestrateAgentId"
Write-Host "  Chat path     : $OrchestrateChatPath"
Write-Host "  Voice provider: $IbmPhoneProvider"
Write-Host "  Phone ready   : $IbmPhoneConfigured"
Write-Host "  WebRTC gateway: $WebRtcGateway"
Write-Host "  WebRTC ready  : $WebRtcGatewayConfigured"
Write-Host "  WebRTC client : $WebRtcSoftphone"
Write-Host "  Min scale     : $MinScale"
Write-Host "  Max scale     : $MaxScale"
Write-Host "  Orchestrate secret: $OrchestrateSecretName"
Write-Host "  Embed auth secret: $EmbedSecretName"
if ($IbmPhoneSecretName) {
    Write-Host "  IBM Phone webhook secret: $IbmPhoneSecretName"
}

if ($DryRun) {
    Write-Host "  [DRY RUN - no live commands will execute]" -ForegroundColor Magenta
}

Invoke-Step "Target IBM Cloud account" "ibmcloud target -g $ResourceGroup -r $Region"
Invoke-Step "Select Code Engine project" "ibmcloud ce project select --name $Project"
Invoke-Step "Verify Code Engine project" "ibmcloud ce project current"
if (-not $OrchestrateBaseUrl) {
    if ($DryRun) {
        $OrchestrateBaseUrl = "<ORCHESTRATE_BASE_URL>"
    }
    else {
        throw "OrchestrateBaseUrl is required for live deployment."
    }
}

if ($OrchestrateBaseUrl -notlike "*/instances/*") {
    if (-not $OrchestrateTenantId) {
        throw "OrchestrateTenantId is required when OrchestrateBaseUrl does not include /instances/{tenant_id}."
    }
    $OrchestrateBaseUrl = $OrchestrateBaseUrl.TrimEnd("/") + "/instances/" + $OrchestrateTenantId
}

$EnvArgs = @(
    '--env "VAB_MCP_TRANSPORT=streamable-http"',
    '--env "VAB_DEMO_HOST=0.0.0.0"',
    "--env `"APP_ENV=$AppEnv`"",
    '--env "ORCHESTRATE_RUNTIME_MODE=remote"',
    "--env `"ORCHESTRATE_BASE_URL=$OrchestrateBaseUrl`"",
    "--env `"ORCHESTRATE_AGENT_ID=$OrchestrateAgentId`"",
    "--env `"ORCHESTRATE_CHAT_PATH=$OrchestrateChatPath`"",
    '--env "ORCHESTRATE_IAM_TOKEN_URL=https://iam.cloud.ibm.com/identity/token"',
    '--env "ORCHESTRATE_TOKEN_REFRESH_SKEW_SECONDS=300"',
    '--env "ORCHESTRATE_TIMEOUT_SECONDS=30"',
    '--env "ORCHESTRATE_MAX_RETRIES=1"',
    '--env "ORCHESTRATE_EMBED_TOKEN_TTL_SECONDS=3600"',
    '--env "EVENT_STREAM_HEARTBEAT_SECONDS=15"',
    '--env "EVENT_STREAM_IDLE_TIMEOUT_SECONDS=300"',
    "--env `"IBM_PHONE_PROVIDER=$IbmPhoneProvider`"",
    "--env `"IBM_PHONE_CHANNEL_CONFIGURED=$($IbmPhoneConfigured.ToString().ToLower())`"",
    "--env `"VAB_WEBRTC_GATEWAY=$WebRtcGateway`"",
    "--env `"VAB_WEBRTC_GATEWAY_CONFIGURED=$($WebRtcGatewayConfigured.ToString().ToLower())`"",
    "--env `"VAB_WEBRTC_SOFTPHONE_ENABLED=$($WebRtcSoftphone.ToString().ToLower())`""
)
if ($WebRtcSignalingUrl) {
    $EnvArgs += "--env `"VAB_WEBRTC_SIGNALING_URL=$WebRtcSignalingUrl`""
}
if ($AllowedUiOrigins) {
    $EnvArgs += "--env MSA_UI_ALLOWED_ORIGINS=$AllowedUiOrigins"
}
$EnvArgString = $EnvArgs -join " "
$SecretArgs = @(
    "--env-from-secret $McpSecretName",
    "--env-from-secret $OrchestrateSecretName",
    "--env-from-secret $EmbedSecretName"
)
if ($IbmPhoneSecretName) {
    $SecretArgs += "--env-from-secret $IbmPhoneSecretName"
}
$SecretArgString = $SecretArgs -join " "

if ($MinScale -lt 0 -or $MaxScale -lt 1 -or $MinScale -gt $MaxScale) {
    throw "Invalid Code Engine scaling: MinScale=$MinScale MaxScale=$MaxScale"
}

Invoke-Step "Update application image and runtime configuration" "ibmcloud ce application update --name $AppName --image $ImageRef --registry-secret $RegistrySecret --min-scale $MinScale --max-scale $MaxScale $EnvArgString $SecretArgString --wait"
Invoke-Step "Get deployed application" "ibmcloud ce application get --name $AppName"

Write-Host ""
Write-Host "Deployment helper complete." -ForegroundColor Green
Write-Host "Validate /health, /readiness, /mcp/version, MCP initialize, tools/list, and get_scheduling_encounter next."
