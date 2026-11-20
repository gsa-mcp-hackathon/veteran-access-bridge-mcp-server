"""Timing correlation must not become an authority or leak across calls."""

import asyncio
import re
import time

import pytest

from veteran_access_bridge.mcp import session_scope as scope


@pytest.mark.asyncio
async def test_separate_request_context_recovers_same_trace_and_resets_on_error():
    observed = []

    async def delegate(name, arguments):
        observed.append(scope.timing_trace_id())
        raise ValueError("test failure")

    async def invoke():
        pytest.fail("Must use scoped delegate")

    with scope.trusted_turn(
        scope.SessionScope("private-case", matched_case="private-case"),
        expires=time.monotonic() + 30,
        workflow=delegate,
    ) as token:
        trace = scope.timing_trace_id()
        assert re.fullmatch(r"[a-f0-9]{32}", trace)
        assert trace not in token
        assert trace not in str(scope.runtime_context())
        from contextvars import Context

        async def remote():
            assert scope.timing_trace_id() == "unscoped"
            with pytest.raises(ValueError):
                await scope.scoped_call(
                    token, "search_call_appointments", "private-case", invoke
                )
            assert scope.timing_trace_id() == "unscoped"

        await asyncio.create_task(remote(), context=Context())
        assert observed == [trace]
        assert scope.timing_trace_id() == trace
    assert scope.timing_trace_id() == "unscoped"
    with pytest.raises(PermissionError):
        await scope.scoped_call(
            trace, "search_call_appointments", "private-case", invoke
        )


def test_nested_turns_restore_distinct_labels():
    state = scope.SessionScope("case")
    with scope.trusted_turn(state, expires=time.monotonic() + 30):
        outer = scope.timing_trace_id()
        with scope.trusted_turn(state, expires=time.monotonic() + 30):
            assert scope.timing_trace_id() != outer
        assert scope.timing_trace_id() == outer
    assert scope.timing_trace_id() == "unscoped"
