"""Numeric-only local durations; diagnostic IDs confer no authority."""

import logging
import time
from contextlib import contextmanager

from veteran_access_bridge.mcp.session_scope import timing_trace_id

STAGES = frozenset({"va_token", "va_resource", "kb_connection", "kb_query"})


@contextmanager
def measured_stage(stage):
    if stage not in STAGES:
        raise ValueError("Unknown timing stage")
    started = time.perf_counter()
    outcome = "error"
    try:
        yield
        outcome = "returned"
    finally:
        logging.getLogger("uvicorn.error.vab_timing").info(
            "VAB source stage=%s duration_ms=%.1f trace_id=%s outcome=%s",
            stage,
            (time.perf_counter() - started) * 1000,
            timing_trace_id(),
            outcome,
        )
