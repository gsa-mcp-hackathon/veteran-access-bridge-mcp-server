"""MCP tool: record_veteran_confirmation.

State-recording — not read-only. Records the Veteran's explicit response to a
confirmation request and advances the lifecycle accordingly:
  CONFIRMED        → PENDING_SCHEDULER_APPROVAL
  DECLINED         → CANCELLED
  REQUESTED_CHANGE → HUMAN_REVIEW

Actor is always VETERAN — not caller-configurable. Only the Veteran may record
this response. SCHEDULER and SYSTEM are rejected.

Idempotent: same idempotency_key + identical response returns the existing record
without appending a duplicate event. Conflicting reuse of idempotency_key fails
closed with no state written.

Preparation of a confirmation request is not consent. This tool records the
explicit Veteran decision only.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastmcp import FastMCP

from veteran_access_bridge.domain.models import ActorRole, VeteranResponse
from veteran_access_bridge.mcp.durable_runtime import require_private_durable_writer
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import confirmation_store as _confirmation_store
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.services.confirmation import (
    ConfirmationStore,
    record_veteran_confirmation,
)
from veteran_access_bridge.services.events import CaseEventStore


def run(
    case_id: str,
    confirmation_request_id: str,
    option_id: str,
    response: str,
    actor_id: str,
    idempotency_key: str,
    *,
    event_store: CaseEventStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
    trusted_gateway: Any = None,
    trusted_assertion: str | None = None,
    verified_evidence_reference: str | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    from veteran_access_bridge.mcp.durable_runtime import scheduling_mode

    if scheduling_mode() == "supabase_test":
        # The public MCP wrapper supplies none of these server-only inputs.
        # Never convert a caller-supplied actor_id into an authorization.
        if (
            trusted_gateway is None
            or not trusted_assertion
            or not verified_evidence_reference
        ):
            require_private_durable_writer()
        if response not in {"CONFIRMED", "DECLINED"}:
            raise PermissionError(
                "Durable change requests require a reviewed signed lifecycle service"
            )
        receipt = trusted_gateway.record_veteran_response_from_trusted_service(
            assertion=trusted_assertion,
            expected_actor_id=actor_id,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=confirmation_request_id,
            verified_evidence_reference=verified_evidence_reference,
            accepted=response == "CONFIRMED",
        )
        return {
            **asdict(receipt),
            "synthetic": True,
            "persistence": "supabase_test",
            "creates_booking": False,
        }
    es = event_store if event_store is not None else _event_store
    cs = confirmation_store if confirmation_store is not None else _confirmation_store

    # Coerce and validate the response string before any state write.
    try:
        veteran_response = VeteranResponse(response)
    except ValueError:
        allowed = [r.value for r in VeteranResponse]
        raise ValueError(f"Invalid response {response!r}. Allowed values: {allowed}.")

    record = record_veteran_confirmation(
        case_id=case_id,
        confirmation_request_id=confirmation_request_id,
        option_id=option_id,
        response=veteran_response,
        actor_role=ActorRole.VETERAN,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        event_store=es,
        confirmation_store=cs,
    )

    payload = to_jsonable(record)
    payload["synthetic"] = True
    payload["creates_booking"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="record_veteran_confirmation",
        annotations={
            "title": "Record Veteran Confirmation",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def record_veteran_confirmation_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
        confirmation_request_id: Annotated[
            str,
            "Confirmation request ID from prepare_veteran_confirmation_request.",
        ],
        option_id: Annotated[str, "Option ID being confirmed."],
        response: Annotated[
            Literal["CONFIRMED", "DECLINED", "REQUESTED_CHANGE"],
            "Veteran's explicit response. CONFIRMED advances to scheduler approval. "
            "DECLINED cancels the case. REQUESTED_CHANGE returns to human review.",
        ],
        actor_id: Annotated[str, "Opaque Veteran identifier (synthetic/demo only)."],
        idempotency_key: Annotated[
            str,
            "Caller-supplied deduplication key. Same key + same response = no-op. "
            "Same key + different response = error.",
        ],
    ) -> dict[str, Any]:
        """Record the Veteran's explicit confirmation response.

        The Veteran's response must be explicit — preparation of a confirmation
        request is not consent. Idempotent: repeated calls with the same
        idempotency_key and identical response return the existing record without
        appending a duplicate event. Conflicting reuse of idempotency_key (different
        response or case) raises an error and writes no state.
        Does not book, reserve, or create scheduler approval.
        """
        return run(
            case_id,
            confirmation_request_id,
            option_id,
            response,
            actor_id,
            idempotency_key,
        )
