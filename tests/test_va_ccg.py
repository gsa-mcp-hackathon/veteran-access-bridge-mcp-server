import base64
import json
from urllib.parse import parse_qs, parse_qsl

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from veteran_access_bridge.adapters.va_ccg import (
    VaCcgClient,
    VaCcgConfig,
    encode_launch,
)


@pytest.fixture
def config():
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return VaCcgConfig("test", "client-test",
                       "https://sandbox-api.va.gov/oauth2/test/system/v1/token",
                       "https://issuer.example/token", "test.read",
                       private_key_pem=pem)


def test_launch_format():
    value = encode_launch({"patient": "5000335", "sta3n": "528"})
    assert json.loads(base64.b64decode(value)) == {"patient": "5000335", "sta3n": "528"}


def test_mock_token_and_caching(config):
    calls = []
    def handler(request):
        calls.append(request)
        fields = dict(parse_qsl(request.content.decode()))
        claims = jwt.decode(
            fields["client_assertion"], options={"verify_signature": False}
        )
        assert claims["iss"] == "client-test"
        assert claims["aud"] == config.audience
        assert fields["scope"] == "test.read"
        return httpx.Response(
            200, json={"access_token": "fixture-token", "expires_in": 3600}
        )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with VaCcgClient(config, http=http) as client:
            assert client.access_token(launch={"patient": "5000335"}) == "fixture-token"
            assert client.access_token(launch={"patient": "5000335"}) == "fixture-token"
    assert len(calls) == 1


def test_token_fail_closed(config):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                401,
                json={
                    "error": "invalid_client",
                    "access_token": "must-not-log",
                },
            )
        )
    ) as http:
        with VaCcgClient(config, http=http) as client:
            with pytest.raises(RuntimeError, match="HTTP 401") as exc:
                client.access_token()
    assert "must-not-log" not in str(exc.value)


def test_disallow_non_va_resource_url(config):
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("must not call network"))) as http:
        with VaCcgClient(config, http=http) as client:
            with pytest.raises(ValueError, match="VA sandbox HTTPS"):
                client.get_json("https://example.com/private")


def test_disallow_non_va_token_url_before_signing_or_network(config):
    config = VaCcgConfig(
        config.name, config.client_id, "https://example.com/token",
        config.audience, config.scope, private_key_pem=config.private_key_pem,
    )
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("must not call network"))) as http:
        with VaCcgClient(config, http=http) as client:
            with pytest.raises(ValueError, match="VA sandbox HTTPS"):
                client.access_token()


def test_resource_read_requires_configured_scope_before_token_request(config):
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("must not call network"))) as http:
        with VaCcgClient(config, http=http) as client:
            with pytest.raises(ValueError, match="required resource scope"):
                client.get_json(
                    "https://sandbox-api.va.gov/fhir/Patient",
                    required_scopes=frozenset({"system/Patient.read"}),
                )


def test_resource_request_uses_launch_scoped_bearer_and_query_params(config):
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "POST":
            form = parse_qs(request.content.decode())
            assert form["scope"] == [config.scope]
            assert json.loads(base64.b64decode(form["launch"][0])) == {
                "patient": "5000335"
            }
            return httpx.Response(
                200, json={"access_token": "fixture-resource-token", "expires_in": 300}
            )

        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer fixture-resource-token"
        assert request.headers["Accept"] == (
            "application/fhir+json, application/json+fhir, application/json"
        )
        assert request.url.params["patient"] == "5000335"
        assert request.url.params["serviceType"] == "Cardiology"
        return httpx.Response(200, json={"resourceType": "Patient", "id": "fixture"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with VaCcgClient(config, http=http) as client:
            client.client_assertion = lambda: "signed-test-assertion"
            result = client.get_json(
                "https://sandbox-api.va.gov/fhir/Patient",
                launch={"patient": "5000335"},
                params={"patient": "5000335", "serviceType": "Cardiology"},
            )

    assert result == {"resourceType": "Patient", "id": "fixture"}
    assert [request.method for request in seen] == ["POST", "GET"]


def test_resource_error_does_not_expose_token_or_response_body(config):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(
                200, json={"access_token": "fixture-secret-token", "expires_in": 300}
            )
        return httpx.Response(
            401, json={"error": "fixture-private-error", "token": "body-secret"}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with VaCcgClient(config, http=http) as client:
            client.client_assertion = lambda: "signed-test-assertion"
            with pytest.raises(RuntimeError, match="HTTP 401") as exc:
                client.get_json(
                    "https://sandbox-api.va.gov/fhir/Patient",
                    launch={"patient": "5000335"},
                )

    message = str(exc.value)
    assert "fixture-secret-token" not in message
    assert "fixture-private-error" not in message
    assert "body-secret" not in message


def test_token_redirect_is_not_followed(config):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://example.com/collect"})

    with httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as http:
        with VaCcgClient(config, http=http) as client:
            with pytest.raises(RuntimeError, match="HTTP 302"):
                client.access_token()

    assert len(seen) == 1
    assert str(seen[0].url) == config.token_url
