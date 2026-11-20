"""Tests for Issue #83 deployed runtime smoke contract."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app
from veteran_access_bridge.app.runtime_smoke import run_runtime_smoke


def test_runtime_smoke_passes_against_local_synthetic_app():
    with TestClient(app) as client:
        report = run_runtime_smoke(client, require_remote=False)

    payload = report.to_dict()
    assert payload["passed"] is True
    assert payload["synthetic"] is True
    assert payload["production_write_attempted"] is False
    assert payload["interaction_id"]
    assert payload["correlation_id"]
    assert payload["runtime_mode"] == "fake"
    assert all(check["passed"] for check in payload["checks"])


def test_runtime_smoke_requires_remote_mode_for_ibm_acceptance():
    with TestClient(app) as client:
        report = run_runtime_smoke(client, require_remote=True)

    payload = report.to_dict()
    assert payload["passed"] is False
    remote = next(
        check for check in payload["checks"] if check["name"] == "remote_runtime_enabled"
    )
    assert remote["passed"] is False
    assert remote["detail"] == "mode=fake"
    assert payload["production_write_attempted"] is False
