"""Correlation contract for live interactions, scheduling encounters, and agent runs.

Issue #80.

This module correlates runtime metadata with the governed Scheduling Encounter.
It does not own scheduling state and does not treat external agent-run status as
authoritative scheduling truth.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
import re


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class InteractionChannel(StrEnum):
    PHONE = "PHONE"
    CHAT = "CHAT"


@dataclass(frozen=True)
class InteractionCorrelation:
    """Stable identifiers joining one live interaction to one encounter."""

    interaction_id: str
    case_id: str
    scheduling_encounter_id: str
    correlation_id: str
    channel: InteractionChannel
    created_at: datetime
    orchestrate_run_id: str | None = None
    orchestrate_session_id: str | None = None
    synthetic: bool = True

    def __post_init__(self) -> None:
        for name in (
            "interaction_id",
            "case_id",
            "scheduling_encounter_id",
            "correlation_id",
        ):
            _validate_identifier(name, getattr(self, name))

        if self.orchestrate_run_id is not None:
            _validate_identifier("orchestrate_run_id", self.orchestrate_run_id)
        if self.orchestrate_session_id is not None:
            _validate_identifier(
                "orchestrate_session_id",
                self.orchestrate_session_id,
            )

        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware.")
        if not self.synthetic:
            raise ValueError("InteractionCorrelation MVP records must be synthetic.")


def _validate_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required.")
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(
            f"{name} must be an opaque machine identifier using only "
            "letters, numbers, dot, underscore, colon, or hyphen."
        )


class CorrelationConflictError(ValueError):
    """Raised when identifiers would ambiguously bind two interactions."""


class CorrelationRegistry:
    """In-memory registry for the synthetic live interaction runtime.

    The same interaction may receive or replace runtime run/session metadata
    during reconnect/retry, but case_id, scheduling_encounter_id, correlation_id,
    and channel remain stable.
    """

    def __init__(self) -> None:
        self._by_interaction: dict[str, InteractionCorrelation] = {}
        self._by_correlation: dict[str, str] = {}
        self._by_run: dict[str, str] = {}
        self._stream_event_ids: set[str] = set()

    def register(self, record: InteractionCorrelation) -> InteractionCorrelation:
        existing = self._by_interaction.get(record.interaction_id)
        if existing is not None:
            if existing == record:
                return existing
            raise CorrelationConflictError(
                f"interaction_id {record.interaction_id!r} is already bound "
                "to different correlation metadata."
            )

        correlation_owner = self._by_correlation.get(record.correlation_id)
        if correlation_owner is not None and correlation_owner != record.interaction_id:
            raise CorrelationConflictError(
                f"correlation_id {record.correlation_id!r} is already in use."
            )

        if record.orchestrate_run_id is not None:
            run_owner = self._by_run.get(record.orchestrate_run_id)
            if run_owner is not None and run_owner != record.interaction_id:
                raise CorrelationConflictError(
                    f"orchestrate_run_id {record.orchestrate_run_id!r} "
                    "is already bound to another interaction."
                )

        self._by_interaction[record.interaction_id] = record
        self._by_correlation[record.correlation_id] = record.interaction_id
        if record.orchestrate_run_id is not None:
            self._by_run[record.orchestrate_run_id] = record.interaction_id
        return record

    def attach_runtime(
        self,
        interaction_id: str,
        *,
        orchestrate_run_id: str,
        orchestrate_session_id: str | None = None,
    ) -> InteractionCorrelation:
        """Attach/replace runtime metadata while preserving encounter identity."""

        record = self.require(interaction_id)
        _validate_identifier("orchestrate_run_id", orchestrate_run_id)
        if orchestrate_session_id is not None:
            _validate_identifier("orchestrate_session_id", orchestrate_session_id)

        owner = self._by_run.get(orchestrate_run_id)
        if owner is not None and owner != interaction_id:
            raise CorrelationConflictError(
                f"orchestrate_run_id {orchestrate_run_id!r} "
                "is already bound to another interaction."
            )

        old_run = record.orchestrate_run_id
        updated = replace(
            record,
            orchestrate_run_id=orchestrate_run_id,
            orchestrate_session_id=orchestrate_session_id,
        )
        self._by_interaction[interaction_id] = updated
        if old_run is not None and old_run != orchestrate_run_id:
            self._by_run.pop(old_run, None)
        self._by_run[orchestrate_run_id] = interaction_id
        return updated

    def require(self, interaction_id: str) -> InteractionCorrelation:
        record = self._by_interaction.get(interaction_id)
        if record is None:
            raise KeyError(f"Unknown interaction_id {interaction_id!r}.")
        return record

    def get_by_correlation_id(
        self,
        correlation_id: str,
    ) -> InteractionCorrelation | None:
        interaction_id = self._by_correlation.get(correlation_id)
        return (
            self._by_interaction[interaction_id]
            if interaction_id is not None
            else None
        )

    def get_by_run_id(self, orchestrate_run_id: str) -> InteractionCorrelation | None:
        interaction_id = self._by_run.get(orchestrate_run_id)
        return (
            self._by_interaction[interaction_id]
            if interaction_id is not None
            else None
        )

    def accept_stream_event(self, event_id: str) -> bool:
        """Return True once per streamed event ID; duplicate deliveries are False."""

        _validate_identifier("event_id", event_id)
        if event_id in self._stream_event_ids:
            return False
        self._stream_event_ids.add(event_id)
        return True
