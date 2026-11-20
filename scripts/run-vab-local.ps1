param(
    [string] $HostAddress = "127.0.0.1",
    [int] $Port = 8080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Import-DotEnv {
    param([string] $Path)

    if (-not (Test-Path $Path)) {
        return
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Import-DotEnv (Join-Path $repoRoot ".env")

if (-not $env:ORCHESTRATE_RUNTIME_MODE) {
    $env:ORCHESTRATE_RUNTIME_MODE = "fake"
}

if ($env:ORCHESTRATE_RUNTIME_MODE.ToLowerInvariant() -ne "remote") {
    throw @"
Veteran Access Bridge local voice requires the real watsonx Orchestrate runtime.

Set non-secret configuration in root .env and API credentials in Codespaces Secrets:
ORCHESTRATE_RUNTIME_MODE=remote
ORCHESTRATE_BASE_URL=<your watsonx Orchestrate API base URL>
ORCHESTRATE_AGENT_ID=89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3
and either:
ORCHESTRATE_API_KEY=<secret>
or
ORCHESTRATE_BEARER_TOKEN=<secret>

The launcher will not silently fall back to the fake runtime for live voice.
"@
}

if (-not $env:ORCHESTRATE_BASE_URL) {
    throw "ORCHESTRATE_BASE_URL is required for local live voice."
}
if (-not $env:ORCHESTRATE_API_KEY -and -not $env:ORCHESTRATE_BEARER_TOKEN) {
    throw "ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN is required for local live voice."
}

# Do not overwrite the configured IBM URL or chat path here.
# Those values depend on the actual Orchestrate tenant and deployment.
if (-not $env:ORCHESTRATE_CHAT_PATH) {
    throw "ORCHESTRATE_CHAT_PATH must be configured in the root .env."
}

Write-Host "Starting Veteran Access Bridge local WebRTC runtime" -ForegroundColor Cyan
Write-Host "  App URL       : http://localhost:$Port"
Write-Host "  WebRTC gateway: $env:VAB_WEBRTC_GATEWAY"
Write-Host "  Signaling URL : $env:VAB_WEBRTC_SIGNALING_URL"
Write-Host "  Softphone     : $env:VAB_WEBRTC_SOFTPHONE_ENABLED"
Write-Host "  Orchestrate   : $env:ORCHESTRATE_RUNTIME_MODE"
Write-Host "  IBM chat URL  : $env:ORCHESTRATE_BASE_URL$($env:ORCHESTRATE_CHAT_PATH.Replace('{agent_id}', $env:ORCHESTRATE_AGENT_ID))"
Write-Host ""

$command = Get-Command veteran-access-demo -ErrorAction SilentlyContinue
if (-not $command) {
    throw "veteran-access-demo is not available. Activate .venv and install the project with voice dependencies."
}

& $command.Source
