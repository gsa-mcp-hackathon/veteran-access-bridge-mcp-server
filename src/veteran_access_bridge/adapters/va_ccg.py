"""Sandbox-only VA OAuth 2.0 client-credentials authentication.

No automatic API enabling; callers supply per-API token metadata, supported scope,
and approved synthetic patient launch fields. Never log assertions or tokens.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import jwt

from veteran_access_bridge.services.latency_timing import measured_stage


def _validate_sandbox_url(url: str, *, token_endpoint: bool = False) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid VA sandbox URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "sandbox-api.va.gov"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only approved VA sandbox HTTPS URLs are permitted")
    if token_endpoint and not re.fullmatch(
        r"/oauth2/[a-z0-9-]+/system/v1/token", parsed.path
    ):
        raise ValueError("Only registered VA sandbox token endpoints are permitted")


def encode_launch(payload: dict[str, str]) -> str:
    if not payload or any(
        not isinstance(value, str) or not value.strip()
        for value in payload.values()
    ):
        raise ValueError("Launch requires nonempty string fields")
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(encoded).decode("ascii")


@dataclass(frozen=True)
class VaCcgConfig:
    name: str
    client_id: str
    token_url: str
    audience: str
    scope: str
    private_key_path: str | None = None
    private_key_pem: str | None = None

    @classmethod
    def from_environment(cls, prefix: str, *, name: str) -> "VaCcgConfig":
        def required(suffix: str) -> str:
            value = os.getenv(f"{prefix}_{suffix}", "").strip()
            if not value:
                raise ValueError(f"Missing {prefix}_{suffix}")
            return value

        return cls(
            name=name,
            client_id=required("CLIENT_ID"),
            token_url=required("TOKEN_URL"),
            audience=required("TOKEN_AUDIENCE"),
            scope=required("SCOPE"),
            private_key_path=os.getenv(f"{prefix}_PRIVATE_KEY_PATH"),
            private_key_pem=os.getenv(f"{prefix}_PRIVATE_KEY_PEM"),
        )

    def key(self) -> str:
        if self.private_key_pem:
            return self.private_key_pem.replace("\\n", "\n")
        if self.private_key_path:
            return Path(self.private_key_path).read_text(encoding="utf-8")
        raise ValueError(f"Missing signing key for {self.name}")


class VaCcgClient:
    def __init__(self, config: VaCcgConfig, *, http: httpx.Client | None = None):
        self.config = config
        self.http = http or httpx.Client(timeout=20, follow_redirects=False)
        self._owns_http = http is None
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> "VaCcgClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def client_assertion(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": self.config.client_id, "sub": self.config.client_id,
             "aud": self.config.audience, "iat": now, "exp": now + 300,
             "jti": str(uuid4())},
            self.config.key(),
            algorithm="RS256",
        )

    def access_token(self, *, launch: dict[str, str] | None = None) -> str:
        _validate_sandbox_url(self.config.token_url, token_endpoint=True)
        launch_value = encode_launch(launch) if launch else ""
        cache_key = (self.config.scope, launch_value)
        token, expiry = self._cache.get(cache_key, ("", 0))
        if token and expiry > time.monotonic() + 60:
            return token
        data = {
            "grant_type": "client_credentials",
            "client_assertion_type": (
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ),
            "client_assertion": self.client_assertion(),
            "scope": self.config.scope,
        }
        if launch_value:
            data["launch"] = launch_value
        with measured_stage("va_token"):
            response = self.http.post(
                self.config.token_url,
                data=data,
                headers={"Accept": "application/json"},
                follow_redirects=False,
            )
        if response.status_code != 200:
            # Response text may contain sensitive context; do not echo it.
            raise RuntimeError(
                f"{self.config.name}: sandbox token exchange failed "
                f"HTTP {response.status_code}"
            )
        body: dict[str, Any] = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"{self.config.name}: token response lacks access_token")
        ttl = max(0, int(body.get("expires_in", 300)))
        self._cache[cache_key] = (token, time.monotonic() + ttl)
        return token

    def get_json(
        self, url: str, *, launch: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        required_scopes: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        _validate_sandbox_url(url)
        if not required_scopes.issubset(set(self.config.scope.split())):
            raise ValueError(
                "Configured VA scope does not include required resource scope"
            )
        token = self.access_token(launch=launch)
        with measured_stage("va_resource"):
            response = self.http.get(
                url, params=params,
                headers={"Authorization": "Bearer " + token,
                         "Accept": (
                             "application/fhir+json, application/json+fhir, "
                             "application/json"
                         )},
                follow_redirects=False,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"{self.config.name}: sandbox resource request failed "
                f"HTTP {response.status_code}"
            )
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result
