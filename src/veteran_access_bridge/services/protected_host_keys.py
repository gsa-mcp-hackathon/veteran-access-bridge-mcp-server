"""Read pinned server keys from protected files or deployment secret variables."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def public_host_key() -> str:
    path = os.getenv("VAB_TRUSTED_HOST_PUBLIC_KEY_PATH", "")
    encoded = os.getenv("VAB_TRUSTED_HOST_PUBLIC_KEY_B64", "")
    if bool(path) == bool(encoded):
        raise PermissionError("Exactly one pinned public key source required")
    try:
        data = (
            Path(path).read_bytes()
            if path
            else base64.b64decode(encoded, validate=True)
        )
        key = serialization.load_pem_public_key(data)
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
            raise ValueError("RSA key required")
        return data.decode("ascii")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise PermissionError("Pinned host public key unavailable") from exc


def private_voice_key():
    path = os.getenv("VAB_TRUSTED_HOST_PRIVATE_KEY_PATH", "")
    encoded = os.getenv("VAB_TRUSTED_HOST_PRIVATE_KEY_B64", "")
    if bool(path) == bool(encoded):
        raise PermissionError("Exactly one protected private key source required")
    if path:
        from veteran_access_bridge.app.synthetic_veteran_host_issuer import _private_key

        return _private_key(path)
    try:
        key = serialization.load_pem_private_key(
            base64.b64decode(encoded, validate=True), password=None
        )
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise ValueError("RSA key required")
        return key
    except (ValueError, TypeError) as exc:
        raise PermissionError("Protected voice signing key unavailable") from exc
