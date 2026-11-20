<#
.SYNOPSIS
    M6.3 remote acceptance for Veteran Access Bridge on IBM Code Engine.

.DESCRIPTION
    Read-only acceptance script for the public Code Engine endpoint.
    Requires VAB_MCP_API_KEY in the current process environment.
    The script never calls a scheduling mutation tool.
#>

param(
    [string] $AppUrl = "https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud",
    [string] $CaseId = "DEMO-CARD-5000335-001",
    [string] $PrimaryCaseId = "DEMO-PC-5000999-001"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:VAB_MCP_API_KEY)) {
    throw "VAB_MCP_API_KEY is required in the current process environment."
}

$McpApiKey = $env:VAB_MCP_API_KEY.Trim()
if ($McpApiKey -notmatch '^[0-9A-Fa-f]{64}$') {
    throw "VAB_MCP_API_KEY must be the 64-character hex bearer credential. Reload the secret without printing it."
}

$AuthHeaders = @{
    "Authorization" = "Bearer $McpApiKey"
    "Accept"        = "application/json, text/event-stream"
}

function Assert-Contains {
    param(
        [string] $Text,
        [string] $Expected,
        [string] $Label
    )
    if ($Text -notmatch [regex]::Escape($Expected)) {
        throw "$Label did not contain expected value: $Expected"
    }
}

Write-Host "==> Health" -ForegroundColor Cyan
$health = Invoke-RestMethod "$AppUrl/health"
if ($health.status -ne "ok") { throw "Health check failed." }
if (-not $health.synthetic) { throw "Expected synthetic=true." }
if ($health.production_writes_enabled) { throw "Production writes must remain disabled." }

Write-Host "==> MCP version" -ForegroundColor Cyan
$version = Invoke-RestMethod "$AppUrl/mcp/version" -Headers $AuthHeaders
if ($version.version -ne "0.4.1") {
    throw "Expected MCP version 0.4.1; got $($version.version)."
}

Write-Host "==> MCP initialize" -ForegroundColor Cyan
$initializeBody = @{
    jsonrpc = "2.0"
    id = 1
    method = "initialize"
    params = @{
        protocolVersion = "2025-03-26"
        capabilities = @{}
        clientInfo = @{
            name = "vab-m63-acceptance"
            version = "0.4.1"
        }
    }
} | ConvertTo-Json -Depth 10

$init = Invoke-WebRequest `
    -Uri "$AppUrl/mcp/" `
    -Method Post `
    -Headers $AuthHeaders `
    -ContentType "application/json" `
    -Body $initializeBody `
    -UseBasicParsing

if ($init.StatusCode -ne 200) { throw "MCP initialize failed." }
$sessionId = $init.Headers["mcp-session-id"]
if ([string]::IsNullOrWhiteSpace($sessionId)) {
    throw "MCP initialize did not return mcp-session-id."
}
Assert-Contains $init.Content "Veteran Access MCP" "initialize"

$SessionHeaders = @{
    "Authorization"  = "Bearer $McpApiKey"
    "Accept"         = "application/json, text/event-stream"
    "mcp-session-id" = $sessionId
}

Write-Host "==> MCP tools/list" -ForegroundColor Cyan
$toolsBody = @{
    jsonrpc = "2.0"
    id = 2
    method = "tools/list"
    params = @{}
} | ConvertTo-Json -Depth 10

$tools = Invoke-WebRequest `
    -Uri "$AppUrl/mcp/" `
    -Method Post `
    -Headers $SessionHeaders `
    -ContentType "application/json" `
    -Body $toolsBody `
    -UseBasicParsing

foreach ($toolName in @(
    "determine_workflow_state",
    "search_availability",
    "assess_access_standard",
    "get_scheduling_encounter"
)) {
    Assert-Contains $tools.Content $toolName "tools/list"
}

Write-Host "==> get_scheduling_encounter" -ForegroundColor Cyan
$encounterBody = @{
    jsonrpc = "2.0"
    id = 3
    method = "tools/call"
    params = @{
        name = "get_scheduling_encounter"
        arguments = @{ case_id = $CaseId }
    }
} | ConvertTo-Json -Depth 10

$encounter = Invoke-WebRequest `
    -Uri "$AppUrl/mcp/" `
    -Method Post `
    -Headers $SessionHeaders `
    -ContentType "application/json" `
    -Body $encounterBody `
    -UseBasicParsing

$expected = @(
    $CaseId,
    "NEW",
    "2026-10-01",
    "OPT-FEHR-SLOT-CARD-5000335-001",
    "35",
    "NOT_EVALUATED",
    "community_care_review_recommended",
    "preferences_create_eligibility",
    "eps_invoked",
    "booking_created"
)
foreach ($value in $expected) {
    Assert-Contains $encounter.Content $value "get_scheduling_encounter"
}

Assert-Contains $encounter.Content '"standard_days":28' "get_scheduling_encounter"
Assert-Contains $encounter.Content '"wait_standard_exceeded":true' "get_scheduling_encounter"
Assert-Contains $encounter.Content '"preferences_create_eligibility":false' "get_scheduling_encounter"
Assert-Contains $encounter.Content '"eps_invoked":false' "get_scheduling_encounter"
Assert-Contains $encounter.Content '"booking_created":false' "get_scheduling_encounter"

Write-Host "==> get_scheduling_encounter (Primary Care)" -ForegroundColor Cyan
$primaryEncounterBody = @{
    jsonrpc = "2.0"
    id = 4
    method = "tools/call"
    params = @{
        name = "get_scheduling_encounter"
        arguments = @{ case_id = $PrimaryCaseId }
    }
} | ConvertTo-Json -Depth 10

$primaryEncounter = Invoke-WebRequest `
    -Uri "$AppUrl/mcp/" `
    -Method Post `
    -Headers $SessionHeaders `
    -ContentType "application/json" `
    -Body $primaryEncounterBody `
    -UseBasicParsing

$primaryExpected = @(
    $PrimaryCaseId,
    "PRIMARY_CARE",
    "ESTABLISHED",
    "2026-11-01",
    "OPT-VISTA-SLOT-PC-5000999-001",
    "14",
    "NOT_EVALUATED"
)
foreach ($value in $primaryExpected) {
    Assert-Contains $primaryEncounter.Content $value "Primary Care get_scheduling_encounter"
}

Assert-Contains $primaryEncounter.Content '"standard_days":20' "Primary Care get_scheduling_encounter"
Assert-Contains $primaryEncounter.Content '"wait_standard_exceeded":false' "Primary Care get_scheduling_encounter"
Assert-Contains $primaryEncounter.Content '"community_care_review_recommended":false' "Primary Care get_scheduling_encounter"
Assert-Contains $primaryEncounter.Content '"preferences_create_eligibility":false' "Primary Care get_scheduling_encounter"
Assert-Contains $primaryEncounter.Content '"eps_invoked":false' "Primary Care get_scheduling_encounter"
Assert-Contains $primaryEncounter.Content '"booking_created":false' "Primary Care get_scheduling_encounter"

Write-Host ""
Write-Host "M6.3 remote acceptance passed." -ForegroundColor Green
Write-Host "  Cardiology : $CaseId"
Write-Host "  Primary Care: $PrimaryCaseId"
Write-Host "  MCP version: $($version.version)"
Write-Host "  Session    : $sessionId"
