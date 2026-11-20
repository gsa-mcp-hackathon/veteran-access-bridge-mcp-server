"""Regression tests for the single canonical WebRTC voice pipeline."""

from importlib.resources import files
from pathlib import Path

import veteran_access_bridge


def _repo_root() -> Path:
    return Path(veteran_access_bridge.__file__).resolve().parents[2]


def test_websocket_voice_does_not_start_browser_stt() -> None:
    app_js = (
        files("veteran_access_bridge.app.static")
        .joinpath("app.js")
        .read_text(encoding="utf-8")
    )
    assert "if (livekitRoom || !voiceMode" in app_js
    livekit_connect = app_js.split("async function connectLiveKitVoice()", 1)[1].split(
        "async function toggleLiveKitVoice()", 1
    )[0]
    assert "stopRecognition();" in livekit_connect
    assert "startRecognition();" not in livekit_connect


def test_websocket_voice_does_not_resynthesize_avery_in_browser() -> None:
    app_js = (
        files("veteran_access_bridge.app.static")
        .joinpath("app.js")
        .read_text(encoding="utf-8")
    )
    agent_block = app_js.split('if (type === "agent_answered")', 1)[1].split(
        'if (type === "mcp_tool_called")', 1
    )[0]
    assert "if (voiceMode && !livekitRoom)" in agent_block


def test_livekit_worker_uses_explicit_flux_turn_controls() -> None:
    worker = (
        _repo_root()
        / "src"
        / "veteran_access_bridge"
        / "voice"
        / "livekit_worker.py"
    ).read_text(encoding="utf-8")
    assert 'DEEPGRAM_EOT_THRESHOLD", "0.7"' in worker
    assert 'DEEPGRAM_EOT_TIMEOUT_MS", "3000"' in worker
    assert 'DEEPGRAM_AUDIO_CHUNK_MS", "80"' in worker
    assert "eager_eot_threshold" not in worker


def test_livekit_meter_uses_published_microphone_track() -> None:
    app_js = (
        files("veteran_access_bridge.app.static")
        .joinpath("app.js")
        .read_text(encoding="utf-8")
    )
    meter_block = app_js.split("async function startMicMeter", 1)[1].split(
        "function stopMicMeter", 1
    )[0]
    assert "navigator.mediaDevices.getUserMedia" not in meter_block
    assert "new MediaStream([mediaTrack])" in meter_block
    connect_block = app_js.split("async function connectLiveKitVoice()", 1)[1].split(
        "async function toggleLiveKitVoice()", 1
    )[0]
    assert "setMicrophoneEnabled(true)" in connect_block
    assert "LiveKit did not publish the Veteran microphone track." in connect_block
    assert "LocalTrackSubscribed" in connect_block


def test_greeting_normalizer_removes_full_existing_greeting() -> None:
    app_js = (
        files("veteran_access_bridge.app.static")
        .joinpath("app.js")
        .read_text(encoding="utf-8")
    )
    normalizer = app_js.split("function stripLeadingGreeting", 1)[1].split(
        "function normalizeAveryReply", 1
    )[0]
    assert "canonicalLower" in normalizer
    assert 'const helpPrompt = "how can i help you?";' in normalizer
