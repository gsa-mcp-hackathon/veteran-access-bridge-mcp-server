from __future__ import annotations

import pytest

from veteran_access_bridge.services.voice_tts import (
    VoiceTTSConfig,
    VoiceTTSService,
    VoiceTTSUnavailable,
)


def test_voice_tts_readiness_hides_credentials() -> None:
    service = VoiceTTSService(
        VoiceTTSConfig(
            provider="ibm",
            ibm_base_url="https://example.text-to-speech.watson.cloud.ibm.com",
            ibm_api_key="secret-key",
            ibm_voice="en-US_EmmaNatural",
        )
    )

    readiness = service.readiness()

    assert readiness == {
        "provider": "ibm",
        "configured": True,
        "voice": "en-US_EmmaNatural",
        "browser_fallback": True,
    }
    assert "secret-key" not in str(readiness)


@pytest.mark.asyncio
async def test_voice_tts_fails_closed_when_neural_provider_not_configured() -> None:
    service = VoiceTTSService(VoiceTTSConfig(provider="browser"))

    with pytest.raises(VoiceTTSUnavailable):
        await service.synthesize("Hello")
