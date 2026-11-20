"""Canonical UI routing: React is opt-in at backend root, legacy remains addressable."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app


def test_backend_root_preserves_legacy_without_web_origin(monkeypatch):
    monkeypatch.delenv("VAB_WEB_UI_URL", raising=False)
    with TestClient(app) as client:
        result = client.get("/")
        assert result.status_code == 200
        assert "Veteran Access Bridge" in result.text


def test_backend_root_can_redirect_to_next_ui(monkeypatch):
    monkeypatch.setenv("VAB_WEB_UI_URL", "http://localhost:3000")
    with TestClient(app, follow_redirects=False) as client:
        result = client.get("/")
        assert result.status_code == 307
        assert result.headers["location"] == "http://localhost:3000/"


def test_legacy_ui_is_stable_when_next_redirect_enabled(monkeypatch):
    monkeypatch.setenv("VAB_WEB_UI_URL", "http://localhost:3000")
    with TestClient(app) as client:
        result = client.get("/legacy")
        assert result.status_code == 200
        assert "Veteran Access Bridge" in result.text


def test_invalid_canonical_ui_url_fails_closed(monkeypatch):
    monkeypatch.setenv("VAB_WEB_UI_URL", "javascript:alert(1)")
    with TestClient(app, follow_redirects=False) as client:
        result = client.get("/")
        assert result.status_code == 503
