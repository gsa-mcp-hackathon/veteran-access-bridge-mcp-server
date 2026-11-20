"""Secure JWT issuance for watsonx Orchestrate embedded chat.

This module is intentionally limited to synthetic/demo identity. The client
private key is loaded only from server-side environment variables and is never
returned to the browser.
"""

from __future__ import annotations

import base64
import os
import time

import jwt


class EmbedAuthConfigurationError(RuntimeError):
    """Raised when embedded-chat signing is not configured safely."""


def _private_key_pem() -> str:
    raw = os.getenv("ORCHESTRATE_EMBED_PRIVATE_KEY", "").strip()
    encoded = os.getenv("ORCHESTRATE_EMBED_PRIVATE_KEY_B64", "").strip()

    if raw:
        return raw.replace("\\n", "\n")
    if encoded:
        try:
            return base64.b64decode(encoded).decode("utf-8").strip()
        except (ValueError, UnicodeDecodeError) as exc:
            raise EmbedAuthConfigurationError(
                "ORCHESTRATE_EMBED_PRIVATE_KEY_B64 is not valid base64 PEM data."
            ) from exc
    raise EmbedAuthConfigurationError(
        "Embedded chat security is not configured. Set "
        "ORCHESTRATE_EMBED_PRIVATE_KEY_B64 (preferred) or "
        "ORCHESTRATE_EMBED_PRIVATE_KEY."
    )


def create_embed_identity_token(
    *,
    subject: str,
    lifetime_seconds: int = 3600,
    now: int | None = None,
) -> tuple[str, int]:
    """Create one short-lived RS256 identity token for IBM embedded chat."""

    clean_subject = subject.strip()
    if not clean_subject:
        raise ValueError("subject is required.")

    # IBM documents a maximum embedded-chat token lifetime of 7100 seconds.
    if lifetime_seconds <= 0 or lifetime_seconds > 7100:
        raise ValueError("lifetime_seconds must be between 1 and 7100.")

    issued_at = int(time.time()) if now is None else int(now)
    expires_at = issued_at + lifetime_seconds
    token = jwt.encode(
        {
            "sub": clean_subject,
            "iat": issued_at,
            "exp": expires_at,
        },
        _private_key_pem(),
        algorithm="RS256",
    )
    return token, expires_at
