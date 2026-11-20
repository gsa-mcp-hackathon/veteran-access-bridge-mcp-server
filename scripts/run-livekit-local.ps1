param(
    [string] $Bind = "127.0.0.1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$server = Get-Command livekit-server -ErrorAction SilentlyContinue

if (-not $server) {
    $knownCandidates = @(
        "C:\Tools\LiveKit\livekit-server.exe",
        "C:\Tools\LiveKit\livekit_1.13.11_windows_amd64\livekit-server.exe"
    )

    foreach ($candidate in $knownCandidates) {
        if (Test-Path $candidate) {
            $server = Get-Item $candidate
            break
        }
    }
}

if (-not $server) {
    $discovered = Get-ChildItem "C:\Tools\LiveKit" -Recurse -Filter "livekit-server.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($discovered) {
        $server = $discovered
    }
}

if (-not $server) {
    throw @"
livekit-server is not installed or could not be found.
Expected PATH or a local installation under C:\Tools\LiveKit.
See docs/operations/open-source-webrtc-voice.md.
"@
}

Write-Host "Starting local LiveKit development server" -ForegroundColor Cyan
Write-Host "  Signaling URL : ws://127.0.0.1:7880"
Write-Host "  Bind          : $Bind"
Write-Host ""
Write-Host "For local development only, set these in your untracked .env:" -ForegroundColor Yellow
Write-Host "  VAB_WEBRTC_GATEWAY=LIVEKIT"
Write-Host "  VAB_WEBRTC_GATEWAY_CONFIGURED=true"
Write-Host "  VAB_WEBRTC_SIGNALING_URL=ws://127.0.0.1:7880"
Write-Host "  VAB_WEBRTC_SOFTPHONE_ENABLED=true"
Write-Host "  LIVEKIT_API_KEY=devkey"
Write-Host "  LIVEKIT_API_SECRET=secret"
Write-Host ""
Write-Host "Do not reuse the LiveKit development credentials in a deployed environment." -ForegroundColor Yellow

$serverPath = if ($server.PSObject.Properties.Name -contains "Source" -and $server.Source) {
    $server.Source
} elseif ($server.PSObject.Properties.Name -contains "FullName" -and $server.FullName) {
    $server.FullName
} else {
    $server.ToString()
}

& $serverPath --dev --bind $Bind
