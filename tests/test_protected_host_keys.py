import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from veteran_access_bridge.services.protected_host_keys import (
    private_voice_key,
    public_host_key,
)


@pytest.fixture
def keys(monkeypatch):
    for side in ("PRIVATE", "PUBLIC"):
        for kind in ("PATH", "B64"):
            monkeypatch.delenv(f"VAB_TRUSTED_HOST_{side}_KEY_{kind}", raising=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return key, private, public


def test_deployment_secret_keypair_is_pinned(keys, monkeypatch):
    key, private, public = keys
    monkeypatch.setenv(
        "VAB_TRUSTED_HOST_PRIVATE_KEY_B64", base64.b64encode(private).decode()
    )
    monkeypatch.setenv(
        "VAB_TRUSTED_HOST_PUBLIC_KEY_B64", base64.b64encode(public).decode()
    )
    assert (
        private_voice_key().public_key().public_numbers()
        == key.public_key().public_numbers()
    )
    assert public_host_key().encode() == public


@pytest.mark.parametrize(
    "value", ["", "not base64!", base64.b64encode(b"not a key").decode()]
)
def test_missing_or_invalid_secret_fails_closed(keys, monkeypatch, value):
    monkeypatch.setenv("VAB_TRUSTED_HOST_PRIVATE_KEY_B64", value)
    monkeypatch.setenv("VAB_TRUSTED_HOST_PUBLIC_KEY_B64", value)
    with pytest.raises(PermissionError):
        private_voice_key()
    with pytest.raises(PermissionError):
        public_host_key()


def test_ambiguous_key_sources_fail_closed(keys, monkeypatch, tmp_path):
    _, private, public = keys
    for side, data in (("PRIVATE", private), ("PUBLIC", public)):
        path = tmp_path / side
        path.write_bytes(data)
        path.chmod(0o600)
        monkeypatch.setenv(f"VAB_TRUSTED_HOST_{side}_KEY_PATH", str(path))
        monkeypatch.setenv(
            f"VAB_TRUSTED_HOST_{side}_KEY_B64", base64.b64encode(data).decode()
        )
    with pytest.raises(PermissionError):
        private_voice_key()
    with pytest.raises(PermissionError):
        public_host_key()
