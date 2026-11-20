"""Server-side text-to-speech adapter for Avery.

Credentials remain server-side. Browser speechSynthesis is a fallback only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class VoiceTTSUnavailable(RuntimeError):
    """Raised when neural text-to-speech is not configured or unavailable."""


@dataclass(frozen=True)
class VoiceTTSConfig:
    provider: str = "browser"
    ibm_base_url: str | None = None
    ibm_api_key: str | None = None
    ibm_voice: str = "en-US_EmmaNatural"
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "VoiceTTSConfig":
        return cls(
            provider=os.getenv("VOICE_TTS_PROVIDER", "browser").strip().lower(),
            ibm_base_url=os.getenv("IBM_TTS_BASE_URL"),
            ibm_api_key=os.getenv("IBM_TTS_API_KEY"),
            ibm_voice=os.getenv("IBM_TTS_VOICE", "en-US_EmmaNatural"),
            timeout_seconds=float(os.getenv("IBM_TTS_TIMEOUT_SECONDS", "15")),
        )


class VoiceTTSService:
    def __init__(self, config: VoiceTTSConfig | None = None) -> None:
        self.config = config or VoiceTTSConfig.from_env()

    def readiness(self) -> dict[str, object]:
        configured = (
            self.config.provider == "ibm"
            and bool(self.config.ibm_base_url)
            and bool(self.config.ibm_api_key)
        )
        return {
            "provider": self.config.provider,
            "configured": configured,
            "voice": self.config.ibm_voice if self.config.provider == "ibm" else None,
            "browser_fallback": True,
        }

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        clean = text.strip()
        if not clean:
            raise ValueError("Text to synthesize must not be empty.")

        if self.config.provider != "ibm":
            raise VoiceTTSUnavailable("Neural TTS provider is not enabled.")

        if not self.config.ibm_base_url or not self.config.ibm_api_key:
            raise VoiceTTSUnavailable("IBM Text to Speech is not configured.")

        url = self.config.ibm_base_url.rstrip("/") + "/v1/synthesize"
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    url,
                    params={"voice": self.config.ibm_voice},
                    headers={"Accept": "audio/mpeg", "Content-Type": "application/json"},
                    auth=httpx.BasicAuth("apikey", self.config.ibm_api_key),
                    json={"text": clean},
                )
        except httpx.HTTPError as exc:
            raise VoiceTTSUnavailable("IBM Text to Speech request failed.") from exc

        if response.status_code >= 400:
            raise VoiceTTSUnavailable(
                f"IBM Text to Speech returned HTTP {response.status_code}."
            )

        if not response.content:
            raise VoiceTTSUnavailable("IBM Text to Speech returned no audio.")

        return response.content, response.headers.get("content-type", "audio/mpeg")
