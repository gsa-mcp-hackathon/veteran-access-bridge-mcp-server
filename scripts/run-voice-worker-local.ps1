param(
    [string] $EnvFile = ".env"
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

Import-DotEnv (Join-Path $repoRoot $EnvFile)

if (-not $env:DEEPGRAM_STT_MODEL) { $env:DEEPGRAM_STT_MODEL = "flux-general-en" }
if (-not $env:DEEPGRAM_TTS_MODEL) { $env:DEEPGRAM_TTS_MODEL = "flux-alexis-en" }
if (-not $env:VAB_VOICE_BACKEND_URL) { $env:VAB_VOICE_BACKEND_URL = "http://127.0.0.1:8080" }
if (-not $env:VAB_VOICE_BACKEND_TIMEOUT_SECONDS) { $env:VAB_VOICE_BACKEND_TIMEOUT_SECONDS = "35" }

if (-not $env:LIVEKIT_URL -or -not $env:LIVEKIT_API_KEY -or -not $env:LIVEKIT_API_SECRET) {
    throw "LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET must come from Codespaces Secrets or secure process environment."
}

if (-not $env:DEEPGRAM_API_KEY) {
    throw @"
DEEPGRAM_API_KEY is missing.

Set DEEPGRAM_API_KEY as a Codespaces Secret or secure process environment variable.
"@
}

Write-Host "Starting Avery LiveKit voice worker" -ForegroundColor Cyan
Write-Host "  LiveKit URL : $env:LIVEKIT_URL"
Write-Host "  STT model   : $env:DEEPGRAM_STT_MODEL"
Write-Host "  TTS model   : $env:DEEPGRAM_TTS_MODEL"
Write-Host "  VAB backend : $env:VAB_VOICE_BACKEND_URL"
Write-Host "  Deepgram key: configured" -ForegroundColor Green
Write-Host ""

$command = Get-Command veteran-access-voice-worker -ErrorAction SilentlyContinue
if (-not $command) {
    throw "veteran-access-voice-worker is not available. Activate .venv and install the project with voice dependencies."
}

& $command.Source dev
