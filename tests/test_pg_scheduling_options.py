"""Case-scoped SQL scheduling reads never imply booking authorization."""

import pytest

from veteran_access_bridge.adapters.pg_scheduling_options import (
    read_scheduling_options,
)


def test_sql_read_disabled(monkeypatch):
    monkeypatch.delenv("VAB_ENABLE_PG_SCHEDULING_READ", raising=False)
    with pytest.raises(PermissionError):
        read_scheduling_options("DEMO-CARD-5000335-001")


def test_sql_read_remote_transport_denied(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_PG_SCHEDULING_READ", "true")
    monkeypatch.setenv("VAB_MCP_TRANSPORT", "streamable-http")
    with pytest.raises(PermissionError):
        read_scheduling_options("DEMO-CARD-5000335-001")


def test_case_scoped_sql_options_real_database(monkeypatch):
    import os

    psycopg = pytest.importorskip("psycopg")
    dsn = os.getenv("VAB_DATABASE_URL")
    if not dsn:
        pytest.skip("Private development PostgreSQL required")
    monkeypatch.setenv("VAB_ENABLE_PG_SCHEDULING_READ", "true")
    monkeypatch.setenv("VAB_MCP_TRANSPORT", "stdio")
    result = read_scheduling_options(
        "DEMO-CARD-5000335-001",
        connect=lambda: psycopg.connect(dsn),
    )
    assert result["synthetic"] is True
    assert result["read_only"] is True
    assert result["booking_writes_enabled"] is False
    assert all(not option["booking_ready"] for option in result["eps_options"])
    assert not result["appointments"]
    assert result["request_id"]
    assert len(result["eps_options"]) == 4
    assert all(option["option_id"] for option in result["eps_options"])
    assert all(option["source_slot_id"] for option in result["eps_options"])
    assert all(not option["booking_ready"] for option in result["eps_options"])
    matched = [
        option
        for option in result["eps_options"]
        if option["option_id"] == "OPT-CC-001"
    ]
    assert len(matched) == 3
    assert all(
        a["association"] == "OPTION_PROVIDER_ONLY" and not a["slot_bound"]
        for option in matched
        for a in option["authorizations"]
    )
    assert all(
        a["option_id"] == option["option_id"]
        and a["provider_id"] == option["provider_id"]
        for option in result["eps_options"]
        for a in option["authorizations"]
    )
