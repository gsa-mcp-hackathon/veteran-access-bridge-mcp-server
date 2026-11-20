from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from veteran_access_bridge.app.embed_auth import create_embed_identity_token


def _test_private_key() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


class EmbedAuthTests(unittest.TestCase):
    def test_rs256_token_contains_synthetic_subject_and_expiry(self):
        private_pem, public_pem = _test_private_key()
        encoded = base64.b64encode(private_pem.encode("utf-8")).decode("ascii")
        with patch.dict(
            os.environ,
            {"ORCHESTRATE_EMBED_PRIVATE_KEY_B64": encoded},
            clear=False,
        ):
            token, expires_at = create_embed_identity_token(
                subject="synthetic-veteran:DEMO-PC-001",
                lifetime_seconds=3600,
                now=1_800_000_000,
            )

        payload = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_exp": False, "verify_iat": False},
        )
        self.assertEqual(payload["sub"], "synthetic-veteran:DEMO-PC-001")
        self.assertEqual(payload["iat"], 1_800_000_000)
        self.assertEqual(payload["exp"], 1_800_003_600)
        self.assertEqual(expires_at, 1_800_003_600)

    def test_token_lifetime_cannot_exceed_ibm_limit(self):
        private_pem, _ = _test_private_key()
        encoded = base64.b64encode(private_pem.encode("utf-8")).decode("ascii")
        with patch.dict(
            os.environ,
            {"ORCHESTRATE_EMBED_PRIVATE_KEY_B64": encoded},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                create_embed_identity_token(
                    subject="synthetic-veteran:DEMO-PC-001",
                    lifetime_seconds=7101,
                )

    def test_embed_token_endpoint_requires_demo_case_scope(self):
        private_pem, _ = _test_private_key()
        encoded = base64.b64encode(private_pem.encode("utf-8")).decode("ascii")
        with patch.dict(
            os.environ,
            {
                "ORCHESTRATE_EMBED_PRIVATE_KEY_B64": encoded,
                "ORCHESTRATE_EMBED_TOKEN_TTL_SECONDS": "3600",
                "VAB_EMBED_TOKEN_SERVICE_KEY": "s" * 48,
            },
            clear=False,
        ):
            from veteran_access_bridge.app.asgi import app

            with TestClient(app, raise_server_exceptions=False) as client:
                ok = client.get(
                    "/api/orchestrate/embed-token",
                    headers={
                        "Authorization": "Bearer " + "s" * 48,
                        "X-Demo-Role": "SCHEDULER",
                        "X-Demo-Actor": "msa-embed-test",
                        "X-Demo-Case": "DEMO-PC-5000335-001",
                    },
                )
                self.assertEqual(ok.status_code, 200)
                body = ok.json()
                self.assertTrue(body["identityToken"])
                self.assertTrue(body["synthetic"])

                forbidden = client.get(
                    "/api/orchestrate/embed-token",
                    headers={
                        "Authorization": "Bearer " + "s" * 48,
                        "X-Demo-Role": "SCHEDULER",
                        "X-Demo-Actor": "msa-embed-test",
                        "X-Demo-Case": "",
                    },
                )
                self.assertEqual(forbidden.status_code, 403)

                # Public synthetic role headers must never mint RS256 tokens.
                forged = client.get(
                    "/api/orchestrate/embed-token",
                    headers={
                        "X-Demo-Role": "SCHEDULER",
                        "X-Demo-Actor": "forged",
                        "X-Demo-Case": "DEMO-PC-5000335-001",
                    },
                )
                self.assertEqual(forged.status_code, 403)

    def test_guest_embed_issuer_is_private_opt_in_and_uses_unique_subjects(self):
        private_pem, public_pem = _test_private_key()
        encoded = base64.b64encode(private_pem.encode("utf-8")).decode("ascii")
        with patch.dict(
            os.environ,
            {
                "ORCHESTRATE_EMBED_PRIVATE_KEY_B64": encoded,
                "VAB_EMBED_TOKEN_SERVICE_KEY": "g" * 48,
                "VAB_EMBED_GUEST_ENABLED": "true",
                "VAB_EMBED_GUEST_TOKEN_TTL_SECONDS": "600",
            },
            clear=False,
        ):
            from veteran_access_bridge.app.asgi import app

            with TestClient(app, raise_server_exceptions=False) as client:
                url = "/api/orchestrate/guest-embed-token"
                guest_a = {"guest_session_id": "a" * 32}
                headers = {"Authorization": "Bearer " + "g" * 48}
                self.assertEqual(client.post(url, json=guest_a).status_code, 403)
                self.assertEqual(
                    client.post(
                        url,
                        headers=headers,
                        json={"case_id": "DEMO-PC-001", **guest_a},
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.post(
                        url, headers=headers, json={"guest_session_id": "bad"}
                    ).status_code,
                    400,
                )
                first = client.post(url, headers=headers, json=guest_a)
                second = client.post(
                    url, headers=headers, json={"guest_session_id": "b" * 32}
                )
                refresh = client.post(url, headers=headers, json=guest_a)
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.headers["cache-control"], "no-store")
                self.assertNotIn("PRIVATE KEY", first.text)

                def payload(response):
                    return jwt.decode(
                        response.json()["identityToken"],
                        public_pem,
                        algorithms=["RS256"],
                    )
                self.assertEqual(payload(first)["sub"], "synthetic-guest:" + "a" * 32)
                self.assertEqual(payload(refresh)["sub"], payload(first)["sub"])
                self.assertNotEqual(payload(first)["sub"], payload(second)["sub"])
                self.assertLessEqual(payload(first)["exp"] - payload(first)["iat"], 900)

        with patch.dict(
            os.environ,
            {
                "ORCHESTRATE_EMBED_PRIVATE_KEY_B64": encoded,
                "VAB_EMBED_TOKEN_SERVICE_KEY": "g" * 48,
                "VAB_EMBED_GUEST_ENABLED": "false",
            },
            clear=False,
        ):
            from veteran_access_bridge.app.asgi import app

            with TestClient(app) as client:
                self.assertEqual(
                    client.post(
                        "/api/orchestrate/guest-embed-token",
                        headers={"Authorization": "Bearer " + "g" * 48},
                        json={"guest_session_id": "a" * 32},
                    ).status_code,
                    403,
                )


if __name__ == "__main__":
    unittest.main()
