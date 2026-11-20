"""Server-only identity assertion issuer for the synthetic session foundation."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from veteran_access_bridge.app.synthetic_veteran_session import SyntheticVeteranSessions
from veteran_access_bridge.services.trusted_primary_care import IDENTITY_SCOPE


def _private_key(path: str) -> rsa.RSAPrivateKey:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise PermissionError("Private host key unavailable") from exc
    with os.fdopen(fd, "rb") as source:
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
        ):
            raise PermissionError("Private host key must be owner-only")
        try:
            key = serialization.load_pem_private_key(source.read(), password=None)
        except (OSError, ValueError, TypeError) as exc:
            raise PermissionError("Private host key unavailable or invalid") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise PermissionError("An RSA host key of at least 2048 bits is required")
    return key


class SyntheticVeteranHostIssuer:
    """Issue only a private identity-scope assertion after session authorization."""

    def __init__(
        self,
        *,
        sessions: SyntheticVeteranSessions,
        issuer: str,
        audience: str,
        subject: str,
        private_key: rsa.RSAPrivateKey,
        public_key: rsa.RSAPublicKey,
    ) -> None:
        if not all(value and value.strip() for value in (issuer, audience, subject)):
            raise PermissionError("Pinned host issuer configuration required")
        if (
            private_key.key_size < 2048
            or private_key.public_key().public_numbers() != public_key.public_numbers()
        ):
            raise PermissionError("Host signing and verifier keys do not match")
        self._sessions = sessions
        self._issuer = issuer
        self._audience = audience
        self._subject = subject
        self._private_key = private_key

    def issue_identity_assertion(self, *, session_cookie: str, case_id: str) -> str:
        binding = self._sessions.authorize(session_cookie, case_id)
        now = int(time.time())
        return jwt.encode(
            {
                "iss": self._issuer,
                "aud": self._audience,
                "sub": self._subject,
                "scope": IDENTITY_SCOPE,
                "case_ids": [binding.case_id],
                "iat": now,
                "exp": now + 60,
                "jti": str(uuid4()),
            },
            self._private_key,
            algorithm="RS256",
        )


def build_synthetic_veteran_host_issuer(
    sessions: SyntheticVeteranSessions,
) -> SyntheticVeteranHostIssuer:
    try:
        issuer = os.environ["VAB_TRUSTED_HOST_ISSUER"]
        audience = os.environ["VAB_TRUSTED_HOST_AUDIENCE"]
        subject = os.environ["VAB_TRUSTED_HOST_SUBJECT"]
        private_path = os.environ["VAB_TRUSTED_HOST_PRIVATE_KEY_PATH"]
        public_pem = Path(os.environ["VAB_TRUSTED_HOST_PUBLIC_KEY_PATH"]).read_bytes()
        public_key = serialization.load_pem_public_key(public_pem)
    except (KeyError, OSError, ValueError, TypeError) as exc:
        raise PermissionError("Host issuer configuration is incomplete") from exc
    private_key = _private_key(private_path)
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise PermissionError("RSA verifier key required")
    return SyntheticVeteranHostIssuer(
        sessions=sessions,
        issuer=issuer,
        audience=audience,
        subject=subject,
        private_key=private_key,
        public_key=public_key,
    )
