"""Purpose-separated, body-bound authentication for trusted final STT turns."""

from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4

import jwt

ISSUER = "vab-avery-voice-worker"
AUDIENCE = "vab-private-voice-turn"


def body_digest(body: dict) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sign_turn(body: dict, secret: str) -> str:
    if len(secret.encode()) < 32:
        raise PermissionError("Dedicated voice worker key required")
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": ISSUER,
            "iat": now,
            "exp": now + 30,
            "jti": str(uuid4()),
            "body_sha256": body_digest(body),
        },
        secret,
        algorithm="HS256",
    )


def verify_turn(token: str, body: dict, secret: str) -> dict:
    if len(secret.encode()) < 32:
        raise PermissionError("Dedicated voice worker key required")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={
                "require": ["iss", "aud", "sub", "iat", "exp", "jti", "body_sha256"]
            },
        )
        if (
            claims["sub"] != ISSUER
            or claims["body_sha256"] != body_digest(body)
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or not 0 < claims["exp"] - claims["iat"] <= 30
            or not isinstance(claims["jti"], str)
            or not claims["jti"]
        ):
            raise PermissionError("Voice turn binding mismatch")
        return claims
    except jwt.PyJWTError as exc:
        raise PermissionError("Invalid voice worker assertion") from exc
