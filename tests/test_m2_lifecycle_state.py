"""M2-9 get_case_lifecycle_state MCP tool tests.

Read-only tool — returns current lifecycle state and optional event history.

Test cases:
 G01  Known case returns found=True with current_state
 G02  Unknown case returns found=False with error
 G03  event_count matches number of seeded events
 G04  last_event_type and last_event_at reflect most recent event
 G05  include_history=False (default) omits event_history key
 G06  include_history=True returns full ordered event_history list
 G07  event_history entries contain expected fields (event_id, from_state, to_state)
 G08  current_state advances correctly after additional events
 G09  synthetic=True always present in response
 G10  Empty store for different case_id returns found=False
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.mcp.tools import get_case_lifecycle_state as gcls_tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CASE = "DEMO-CARD-M29-001"
_SCHED_ID = "sched-demo-m29"
_T0 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_store() -> CaseEventStore:
    return CaseEventStore()


def _seed_event(
    store: CaseEventStore,
    case_id: str,
    from_state: CaseLifecycleState,
    to_state: CaseLifecycleState,
    event_type: CaseEventType,
    idem_key: str,
) -> CaseEvent:
    return store.append(CaseEvent(
        event_id="seed-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16],
        case_id=case_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        occurred_at=_T0,
        idempotency_key=idem_key,
        payload={},
    ))


def _seed_to_human_review(store: CaseEventStore, case_id: str = _CASE) -> None:
    """Seed a case through to HUMAN_REVIEW."""
    _seed_event(store, case_id,
        CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
        CaseEventType.WORKFLOW_GATE_EVALUATED, f"g-rr-{case_id}")
    _seed_event(store, case_id,
        CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
        CaseEventType.SEARCH_EXECUTED, f"g-rts-{case_id}")
    _seed_event(store, case_id,
        CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
        CaseEventType.OPTIONS_ASSESSED, f"g-va-{case_id}")
    _seed_event(store, case_id,
        CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
        CaseEventType.HANDOFF_PREPARED, f"g-rfh-{case_id}")


# ---------------------------------------------------------------------------
# G01 — Known case returns found=True with current_state
# ---------------------------------------------------------------------------

def test_g01_known_case_found():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es)
    assert result["found"] is True
    assert result["current_state"] == "HUMAN_REVIEW"


# ---------------------------------------------------------------------------
# G02 — Unknown case returns found=False
# ---------------------------------------------------------------------------

def test_g02_unknown_case_not_found():
    es = _fresh_store()
    result = gcls_tool.run("CASE-DOES-NOT-EXIST", event_store=es)
    assert result["found"] is False
    assert "error" in result
    assert "CASE-DOES-NOT-EXIST" in result["error"]


# ---------------------------------------------------------------------------
# G03 — event_count matches seeded events
# ---------------------------------------------------------------------------

def test_g03_event_count():
    es = _fresh_store()
    _seed_to_human_review(es)  # 4 events
    result = gcls_tool.run(_CASE, event_store=es)
    assert result["event_count"] == 4


# ---------------------------------------------------------------------------
# G04 — last_event_type and last_event_at reflect most recent event
# ---------------------------------------------------------------------------

def test_g04_last_event_fields():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es)
    assert result["last_event_type"] == "HANDOFF_PREPARED"
    assert result["last_event_at"] == _T0.isoformat()


# ---------------------------------------------------------------------------
# G05 — include_history=False omits event_history
# ---------------------------------------------------------------------------

def test_g05_no_history_by_default():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es)
    assert "event_history" not in result


def test_g05b_no_history_explicit_false():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es, include_history=False)
    assert "event_history" not in result


# ---------------------------------------------------------------------------
# G06 — include_history=True returns full ordered event_history list
# ---------------------------------------------------------------------------

def test_g06_include_history():
    es = _fresh_store()
    _seed_to_human_review(es)  # 4 events
    result = gcls_tool.run(_CASE, event_store=es, include_history=True)
    assert "event_history" in result
    assert len(result["event_history"]) == 4


# ---------------------------------------------------------------------------
# G07 — event_history entries have expected fields
# ---------------------------------------------------------------------------

def test_g07_history_entry_fields():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es, include_history=True)
    first = result["event_history"][0]
    assert "event_id" in first
    assert "from_state" in first
    assert "to_state" in first
    assert "event_type" in first
    assert "actor_role" in first
    assert "occurred_at" in first
    # First event: REQUEST_RECEIVED → READY_TO_SEARCH
    assert first["from_state"] == "REQUEST_RECEIVED"
    assert first["to_state"] == "READY_TO_SEARCH"


# ---------------------------------------------------------------------------
# G08 — current_state advances correctly after additional events
# ---------------------------------------------------------------------------

def test_g08_state_advances():
    es = _fresh_store()
    _seed_to_human_review(es)
    # Initially HUMAN_REVIEW
    r1 = gcls_tool.run(_CASE, event_store=es)
    assert r1["current_state"] == "HUMAN_REVIEW"

    # Advance to OPTION_SELECTED
    _seed_event(es, _CASE,
        CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
        CaseEventType.OPTION_SELECTED, "g-hr-opt")
    r2 = gcls_tool.run(_CASE, event_store=es)
    assert r2["current_state"] == "OPTION_SELECTED"
    assert r2["event_count"] == 5


# ---------------------------------------------------------------------------
# G09 — synthetic=True always present
# ---------------------------------------------------------------------------

def test_g09_synthetic_flag_found():
    es = _fresh_store()
    _seed_to_human_review(es)
    result = gcls_tool.run(_CASE, event_store=es)
    assert result["synthetic"] is True


def test_g09b_synthetic_flag_not_found():
    es = _fresh_store()
    result = gcls_tool.run("CASE-MISSING", event_store=es)
    assert result["synthetic"] is True


# ---------------------------------------------------------------------------
# G10 — Different case_id returns found=False when only one case seeded
# ---------------------------------------------------------------------------

def test_g10_different_case_id_not_found():
    es = _fresh_store()
    _seed_to_human_review(es, case_id=_CASE)
    result = gcls_tool.run("DEMO-CARD-M29-DIFFERENT", event_store=es)
    assert result["found"] is False
