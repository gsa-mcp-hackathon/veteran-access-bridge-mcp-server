"""Opt-in synthetic voice host. No booking authority comes from LLM/tool output.

A token issued by this backend binds one canonical call to one participant.
Authenticated worker turns are checked against LiveKit's current participant,
then a deterministic dialogue collects identity answers and explicit slot consent.
Process restart discards call authority; it never silently reconstructs consent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
    connect_private_supabase_test_scheduling_readonly,
)
from veteran_access_bridge.app.private_primary_care_booking import (
    APPROVED_CASE,
    _verified_receipt,
    build_private_booking_from_environment,
)
from veteran_access_bridge.app.synthetic_veteran_consent import (
    verified_consent_evidence,
)
from veteran_access_bridge.mcp.session_scope import (
    SessionScope,
    timing_trace_id,
    trusted_turn,
    turn_receipts,
)
from veteran_access_bridge.services.demo_facility_context import (
    configured_facilities,
    resolve_demo_facility,
)
from veteran_access_bridge.services.pg_governed_va_commit import SCOPE, VABookingRequest
from veteran_access_bridge.services.pg_signed_decisions import (
    AUDIENCE as DECISION_AUDIENCE,
)
from veteran_access_bridge.services.pg_signed_decisions import ISSUER as DECISION_ISSUER
from veteran_access_bridge.services.supabase_scheduling_gateway import (
    PrivateSyntheticSchedulingGateway,
)
from veteran_access_bridge.services.trusted_primary_care import (
    CASE_PROVISION_SCOPE,
    IDENTITY_SCOPE,
    RECOVERY_SCOPE,
    TrustedHostAuthenticator,
    verify_and_record_synthetic_identity,
)
from veteran_access_bridge.voice.appointment_language import (
    explicitly_confirms,
    local_appointment_time,
    spoken_zone,
)
from veteran_access_bridge.voice.identity_intake import IdentityIntake
from veteran_access_bridge.voice.spoken_identity import spoken_birth_date, spoken_name
from veteran_access_bridge.voice.spoken_last_four import (
    VERIFICATION_PROMPT,
    redact_spoken_identity,
    split_last_four,
)
from veteran_access_bridge.voice.worker_assertion import verify_turn

OPENING = (
    "Yes, I can assist with scheduling your appointment. "
    "First, I need to verify your identity. Please say your full name."
)
INTAKE_CASE = "DEMO-PC-VOICE-INTAKE-001"


class NoVerifiedAppointment(PermissionError):
    """No current case-bound offer passed the existing evidence checks."""


class VoiceTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_session_id: str = Field(min_length=1, max_length=128)
    room_name: str = Field(min_length=1, max_length=140)
    participant_identity: str = Field(min_length=1, max_length=128)
    participant_sid: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=0, le=10000)
    action: Literal["opening", "turn", "last_four"]
    text: str = Field(default="", max_length=512, repr=False)


@dataclass
class BoundCall:
    case_id: str
    room_name: str
    participant_identity: str
    expires: float
    interaction_id: str = ""
    participant_sid: str | None = None
    sequence: int = 0
    stage: str = "NEW"
    name: str = field(default="", repr=False)
    identity_operation: str | None = None
    require_mcp_identity: bool = False
    verified_first_name: str = field(default="", repr=False)
    identity: object | None = None
    offer: dict | None = None
    request: VABookingRequest | None = None
    protected: BoundCall | None = None
    receipt: dict | None = None
    crm_note: dict | None = None
    crm_note_status: str | None = None
    used: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    mcp_scope: SessionScope | None = field(default=None, repr=False)
    patient_zone: str | None = None
    facility_context: dict | None = None
    patient_source_verified: bool = False
    options: list[dict] = field(default_factory=list, repr=False)
    options_sequence: int | None = None
    readback_sequence: int | None = None
    trusted_reply: str | None = None
    identity_intake: IdentityIntake | None = field(default=None, repr=False)
    ended: bool = False
    end_reason: str | None = None
    after_call: dict | None = field(default=None, repr=False)
    case_booking: object | None = field(default=None, repr=False)


class TrustedVoiceBooking:
    def __init__(
        self,
        *,
        worker_secret,
        issuer,
        audience,
        subject,
        private_key,
        authenticator,
        booking,
        gateway,
        decision_secret,
        connect,
        read_connect,
        participant_lookup,
        conversations=None,
        approved_case=APPROVED_CASE,
        browser_booking=False,
        intake_lookup=None,
        agent_scheduling=False,
        patient_reader=None,
        knowledge_reader=None,
        slot_refresher=None,
        caller_resolver=None,
        booking_factory=None,
    ):
        if len(worker_secret.encode()) < 32 or len(decision_secret.encode()) < 32:
            raise PermissionError("Protected voice credentials required")
        if not all((issuer, audience, subject)):
            raise PermissionError("Pinned voice host required")
        self.worker_secret = worker_secret
        self.issuer, self.audience, self.subject = issuer, audience, subject
        self.private_key, self.authenticator = private_key, authenticator
        self.booking, self.gateway, self.decision_secret = (
            booking,
            gateway,
            decision_secret,
        )
        self.connect, self.read_connect = connect, read_connect
        self.participant_lookup = participant_lookup
        self.conversations = conversations
        if not re.fullmatch(r"VAB-DEMO-20261113-CASE-\d{3}", approved_case):
            raise PermissionError("One explicit synthetic fixture case required")
        if browser_booking and (conversations is None or intake_lookup is None):
            raise PermissionError(
                "IBM conversation and authenticated MCP intake required"
            )
        self.approved_case = approved_case
        self.browser_booking = browser_booking
        self.intake_lookup = intake_lookup
        self.agent_scheduling = agent_scheduling
        self.patient_reader = patient_reader
        self.knowledge_reader = knowledge_reader
        self.slot_refresher = slot_refresher
        if caller_resolver is not None and (
            not agent_scheduling or booking_factory is None
        ):
            raise PermissionError("Dynamic callers require the governed agent workflow")
        if os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") == "true" and (
            not agent_scheduling or caller_resolver is None
        ):
            raise PermissionError(
                "Masked identity requires the dynamic caller workflow"
            )
        self.caller_resolver = caller_resolver
        if os.getenv("VAB_SPOKEN_LAST_FOUR") == "true" and (
            os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") != "true"
        ):
            raise PermissionError("Spoken factor requires source verification")
        self.booking_factory = booking_factory
        self.calls: dict[str, BoundCall] = {}

    def _booking_for(self, call):
        if self.caller_resolver is None:
            return self.booking
        if (
            call.identity is None
            or not self.caller_resolver.bound(
                call.case_id, call.identity.correlation_id
            )
            or call.case_booking is None
        ):
            raise PermissionError("Call-bound booking service required")
        return call.case_booking

    def bind(
        self,
        *,
        voice_session_id,
        case_id,
        room_name,
        participant_identity,
        interaction_id="",
    ):
        intake = case_id == INTAKE_CASE and self.conversations is not None
        if self.caller_resolver is not None and not intake:
            raise PermissionError("Dynamic callers must start in authenticated intake")
        if (
            case_id != self.approved_case and not intake
        ) or room_name != "vab-" + voice_session_id:
            raise PermissionError("Only the approved synthetic voice case is enabled")
        if intake:
            snapshot = self.conversations.snapshot(interaction_id)
            if (
                snapshot.correlation.case_id != INTAKE_CASE
                or snapshot.runtime_failure_code is not None
                or snapshot.runtime_interaction is None
            ):
                raise PermissionError("Canonical IBM intake interaction required")
        now = time.monotonic()
        self.calls = {k: v for k, v in self.calls.items() if v.expires > now}
        if voice_session_id in self.calls or len(self.calls) >= 32:
            raise PermissionError("Call already bound or capacity reached")
        self.calls[voice_session_id] = BoundCall(
            case_id,
            room_name,
            participant_identity,
            now + 900,
            interaction_id=interaction_id,
        )

    def _assertion(self, bound_case, scope, **claims):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": self.issuer,
                "aud": self.audience,
                "sub": self.subject,
                "iat": now,
                "exp": now + 60,
                "jti": str(uuid4()),
                "scope": scope,
                "case_ids": [bound_case],
                **claims,
            },
            self.private_key,
            algorithm="RS256",
        )

    async def renew_call(self, session):
        """Renew media lifecycle only after checking the original live participant.

        Identity evidence, consent and signed tool grants keep their own expiry.
        A browser heartbeat cannot recreate an expired or ended call.
        """
        call = self.calls.get(session.voice_session_id)
        if call is None:
            raise PermissionError("Unknown call")
        async with call.lock:
            if (
                call.ended
                or call.expires <= time.monotonic()
                or session.state.value != "CONNECTED"
                or session.interaction_id != call.interaction_id
                or session.case_id != call.case_id
                or call.participant_sid is None
            ):
                raise PermissionError("Active bound call required")
            participant = await self.participant_lookup(
                call.room_name, call.participant_identity
            )
            if (
                participant.identity != call.participant_identity
                or participant.sid != call.participant_sid
                or call.ended
                or call.expires <= time.monotonic()
            ):
                raise PermissionError("Current original participant required")
            if (
                self.caller_resolver is not None
                and call.protected is not None
                and call.protected.identity is not None
            ):
                await run_in_threadpool(
                    self.caller_resolver.renew,
                    call.protected.case_id,
                    session.voice_session_id,
                )
            call.expires = time.monotonic() + 900
            if call.protected is not None:
                call.protected.expires = call.expires
            return {
                "ok": True,
                "voice_session_id": session.voice_session_id,
                "synthetic": True,
            }

    async def finalize_call(self, session, reason="CALLER_ENDED"):
        """Only the authenticated canonical terminal-event handler invokes this."""
        from veteran_access_bridge.services.after_call import (
            prepare_wrapup,
            record_after_call,
        )

        voice = session.voice_session_id
        call = self.calls.get(voice)
        if (
            session.state.value not in {"ENDED", "FAILED"}
            or call is None
            or call.interaction_id != session.interaction_id
            or call.case_id != session.case_id
        ):
            return {"status": "UNAVAILABLE", "persisted": False}
        # Revoke new turns/tools immediately, even if an earlier turn still holds
        # the lock. Reconcile any already-started commit before preparing wrap-up.
        call.ended = True
        if call.protected is not None:
            call.protected.ended = True
        async with call.lock:
            call.end_reason = call.end_reason or reason
            if call.after_call is not None:
                return call.after_call
            protected = call.protected or call
            call.name = protected.name = ""
            call.verified_first_name = protected.verified_first_name = ""
            if protected.identity_intake is not None:
                protected.identity_intake.clear()
            identity = protected.identity
            if (
                identity is None
                or not identity.verified
                or identity.correlation_id != voice
                or identity.case_id != protected.case_id
            ):
                call.after_call = {
                    "status": "NOT_SAVED_UNVERIFIED",
                    "persisted": False,
                    "letter": None,
                    "reason": call.end_reason,
                }
                return call.after_call

            def verify():
                if not call.ended or self.calls.get(voice) is not call:
                    raise PermissionError("Terminal bound call required")
                receipt = None
                if protected.receipt is not None:
                    request = protected.request
                    recovered = self._booking_for(protected).recover(
                        request=request,
                        assertion=self._assertion(
                            protected.case_id,
                            RECOVERY_SCOPE,
                            case_id=protected.case_id,
                            option_id=request.option_id,
                            slot_id=str(request.slot_id),
                            idempotency_key=request.idempotency_key,
                            voice_session_id=voice,
                        ),
                    )
                    receipt = _verified_receipt(recovered, protected.case_id)
                    if receipt != protected.receipt:
                        raise PermissionError("Booking readback changed")
                elif protected.stage in {"COMMITTING", "BOOKED"}:
                    raise PermissionError("Booking outcome requires reconciliation")
                return prepare_wrapup(
                    case_id=protected.case_id,
                    voice_session_id=voice,
                    reason=call.end_reason,
                    receipt=receipt,
                    patient_zone=protected.patient_zone,
                    facility_name=(protected.facility_context or {}).get("name"),
                    declined=protected.stage == "DECLINED",
                )

            try:
                result = await run_in_threadpool(
                    record_after_call,
                    case_id=protected.case_id,
                    interaction_id=call.interaction_id,
                    voice_session_id=voice,
                    verify=verify,
                )
                if self.caller_resolver is not None:
                    await run_in_threadpool(
                        self.caller_resolver.finish, protected.case_id, voice
                    )
                call.after_call = result
                return result
            except Exception:
                return {"status": "PENDING", "persisted": False, "letter": None}

    async def handle(self, body: VoiceTurn, token: str):
        claims = verify_turn(token, body.model_dump(), self.worker_secret)
        call = self.calls.get(body.voice_session_id)
        if call is None:
            raise PermissionError("Call was not issued by this host")
        async with call.lock:
            if (
                call.ended
                or call.expires <= time.monotonic()
                or body.room_name != call.room_name
                or body.participant_identity != call.participant_identity
                or body.sequence != call.sequence
                or claims["jti"] in call.used
                or (
                    call.participant_sid is not None
                    and call.participant_sid != body.participant_sid
                )
            ):
                raise PermissionError("Call binding expired, changed, or replayed")
            participant = await self.participant_lookup(
                call.room_name, call.participant_identity
            )
            if (
                participant.identity != call.participant_identity
                or participant.sid != body.participant_sid
            ):
                raise PermissionError("Current LiveKit participant required")
            if call.expires <= time.monotonic():
                raise PermissionError("Call expired during participant verification")
            call.participant_sid = body.participant_sid
            call.used.add(claims["jti"])
            call.sequence += 1
            diagnostic_trace = None
            try:
                if call.case_id == INTAKE_CASE:
                    if call.mcp_scope is None:
                        call.mcp_scope = SessionScope(
                            call.case_id,
                            interaction_id=call.interaction_id,
                            private_identity=self.agent_scheduling
                            and self.caller_resolver is not None
                            and os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") == "true",
                        )
                    prior_events = len(
                        self.conversations.events.get_events(call.interaction_id)
                    )
                    with trusted_turn(
                        call.mcp_scope,
                        expires=call.expires,
                        crm_enabled=os.getenv("VAB_ENABLE_CRM") == "true",
                        workflow=(
                            lambda name, args: self._agent_tool(call, body, name, args)
                        )
                        if self.agent_scheduling
                        else None,
                        is_active=lambda: (
                            not call.ended
                            and call.stage != "HALTED"
                            and self.conversations.snapshot(
                                call.interaction_id
                            ).status.value
                            != "CALL_ENDED"
                        ),
                    ) as turn_scope:
                        diagnostic_trace = timing_trace_id()
                        answer = await self._conversation_turn(call, body)
                        if not call.mcp_scope.halted:
                            completed = self._project_scope_receipts(
                                call, turn_receipts(turn_scope), prior_events
                            )
                            if call.protected and call.protected.stage == "VERIFY":
                                answer = await self._finish_verification(
                                    call, completed
                                )
                else:
                    answer = await run_in_threadpool(self._advance, call, body)
            except Exception as exc:
                # Locations and exception types only: never log caller speech,
                # credential-bearing exception text, request bodies or locals.
                logging.getLogger(__name__).error(
                    "Voice turn failed type=%s frames=%s",
                    type(exc).__name__,
                    [
                        (frame.name, frame.lineno)
                        for frame in traceback.extract_tb(exc.__traceback__)
                    ],
                )
                call.stage = "HALTED"
                call.name = ""
                raise
            return {
                "synthetic": True,
                "voice_session_id": body.voice_session_id,
                "stage": call.stage,
                "requires_last_four": (
                    (call.protected or call).stage == "LAST_FOUR"
                    and os.getenv("VAB_SPOKEN_LAST_FOUR") != "true"
                ),
                "identity_pending": (call.protected or call).identity is None,
                "silence_prompt": self._silence_prompt(call.protected or call),
                "text": answer,
                "timing_trace_id": diagnostic_trace,
                # Protect the audible offer, consent reminder and final outcome.
                # This is delivery policy, not authority to accept fragmented consent.
                "allow_interruptions": (call.protected or call).stage
                not in {"CONFIRM", "COMMITTING", "BOOKED", "DECLINED", "HALTED"},
            }

    @staticmethod
    def _silence_prompt(call):
        intake = call.identity_intake
        if call.stage == "LAST_FOUR" and os.getenv("VAB_SPOKEN_LAST_FOUR") == "true":
            field = "last four digits"
        elif call.stage == "IDENTITY_CONFIRM":
            return (
                "Sorry, I didn't hear your response. Did I get your "
                "name and date of birth right?"
            )
        elif call.stage == "DOB" or (
            call.stage == "NAME" and intake and len(intake.name.split()) >= 2
        ):
            field = "date of birth"
        elif call.stage == "NAME":
            field = "last name" if intake and intake.name else "full name"
        else:
            return None
        return f"Sorry, I didn't catch your {field}. Could you say it again?"

    async def _finish_verification(self, call, completed):
        protected = call.protected
        if "verify_synthetic_identity" not in completed:
            protected.stage = "HALTED"
            call.stage = "HALTED"
            if protected.identity_operation:
                self._project(
                    call,
                    "mcp_tool_result",
                    {
                        "tool_name": "verify_synthetic_identity",
                        "tool_call_id": protected.identity_operation,
                        "status": "blocked",
                        "verified": False,
                    },
                )
            protected.identity = None
            return (
                "I couldn't complete verification. Please contact your scheduling team."
            )
        call.mcp_scope.matched_case = protected.case_id
        self._project(call, "voice_identity_verified", {})
        return await run_in_threadpool(self._identity_reply, protected)

    async def _conversation_turn(self, call, body):
        """Route bound intake audio to IBM, without granting booking authority.

        The interaction ID comes only from the server's canonical VoiceSession.
        Caller metadata, tool output and identity matches cannot switch this
        call into the separately approved booking state machine.
        """
        from veteran_access_bridge.domain import (
            InteractionEventSource,
            InteractionEventType,
        )

        snapshot = self.conversations.snapshot(call.interaction_id)
        if (
            snapshot.correlation.case_id != INTAKE_CASE
            or snapshot.status.value == "CALL_ENDED"
            or snapshot.runtime_failure_code is not None
            or call.stage == "HALTED"
        ):
            raise PermissionError("Canonical intake scope changed")
        if call.protected is not None:
            if body.action not in {"turn", "last_four"}:
                raise PermissionError("Protected intake cannot restart")
            if body.action == "last_four" and call.protected.stage != "LAST_FOUR":
                raise PermissionError("Private identity input is not expected")
            previous = call.protected.stage
            if self.agent_scheduling and previous in {"AGENT", "CONFIRM", "BOOKED"}:
                return await self._agent_conversation(call, body)
            answer = await run_in_threadpool(self._advance, call.protected, body)
            if (
                call.mcp_scope.private_identity
                and previous in {"NAME", "DOB", "IDENTITY_CONFIRM", "LAST_FOUR"}
                and call.protected.identity is not None
                and call.protected.identity.verified
                and call.protected.stage == "VERIFY"
            ):
                call.mcp_scope.workflow_context = {"vab_workflow_stage": "VERIFY"}
                await self.conversations.send_message(
                    interaction_id=call.interaction_id,
                    message=(
                        "Call verify_synthetic_identity once using the current "
                        "intake case_id and session_scope. "
                        "Use PRIVATE for both full_name and birth_date. "
                        "The voice service holds the answers. Do not ask again."
                    ),
                    _application_event=True,
                )
                return ""
            if previous in {"NAME", "DOB", "IDENTITY_CONFIRM", "LAST_FOUR"} and (
                call.protected.identity
                and call.protected.identity.verified
                and call.protected.stage in {"FACILITY", "TIMEZONE", "CONFIRM"}
            ):
                self._project(call, "voice_identity_verified", {})
            prior_note = call.protected.crm_note_status
            if call.protected.stage == "BOOKED":
                await run_in_threadpool(self._record_booking_note, call)
                if call.protected.crm_note_status == "SAVED":
                    answer += " An automatic booking summary has been saved to CRM."
                elif call.protected.crm_note_status == "PENDING":
                    answer += (
                        " The appointment remains confirmed, but the automatic "
                        "CRM note is not yet confirmed saved."
                    )
            if call.protected.stage != previous or (
                call.protected.crm_note_status != prior_note
            ):
                self._project_booking(call)
            return answer
        if body.action == "last_four":
            raise PermissionError("Private identity input is not expected")
        if body.action == "opening":
            if call.stage != "NEW" or body.text:
                raise PermissionError("Opening cannot reset call state")
            answers = [
                event
                for event in self.conversations.events.get_events(call.interaction_id)
                if event.event_type == InteractionEventType.AGENT_ANSWERED
                and event.source == InteractionEventSource.WATSONX_ORCHESTRATE
            ]
            if not answers:
                raise PermissionError("Verified IBM opening unavailable")
            event = answers[-1]
            if event.payload.get("text", "").strip() == "Skill has stopped processing":
                # Startup precedes RTC binding and may be denied by IBM's guard.
                # This handler already verified the worker and participant, and
                # is inside trusted_turn. Retry only the greeting with that real
                # capability; never fabricate an IBM response or caller utterance.
                from veteran_access_bridge.domain.avery_script import (
                    build_unselected_incoming_call_instruction,
                )

                event = await self.conversations.send_message(
                    interaction_id=call.interaction_id,
                    message=build_unselected_incoming_call_instruction(),
                    _application_event=True,
                )
        else:
            if call.stage != "CONVERSATION" or not body.text.strip():
                raise PermissionError("Active intake conversation required")
            event = await self.conversations.send_message(
                interaction_id=call.interaction_id,
                message=(
                    redact_spoken_identity(
                        body.text.strip(),
                        identity_phase=split_last_four(body.text)[2],
                    )
                    if os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
                    else body.text.strip()
                ),
            )
        if (
            event.event_type != InteractionEventType.AGENT_ANSWERED
            or event.source != InteractionEventSource.WATSONX_ORCHESTRATE
            or event.interaction_id != call.interaction_id
            or event.case_id != INTAKE_CASE
        ):
            raise PermissionError("IBM response unavailable or out of scope")
        answer = event.payload.get("text")
        if not isinstance(answer, str) or not answer.strip():
            raise PermissionError("IBM response contains no speech")
        if answer.strip() == "Skill has stopped processing":
            raise PermissionError("IBM denied the authenticated voice turn")
        call.stage = "CONVERSATION"
        from veteran_access_bridge.app.browser_primary_care import (
            primary_care_requested,
        )

        if (
            self.browser_booking
            and body.action == "turn"
            and primary_care_requested(body.text)
        ):
            tool_id = "voice-intake-" + body.voice_session_id
            self._project(
                call,
                "mcp_tool_called",
                {
                    "tool_name": "get_scheduling_encounter",
                    "tool_call_id": tool_id,
                    "status": "started",
                },
            )
            try:
                # A separate host-only capability can read only the empty intake
                # fixture. It is never sent to IBM and grants no patient reads.
                with trusted_turn(
                    SessionScope(INTAKE_CASE),
                    expires=call.expires,
                    host_intake=True,
                    is_active=lambda: (
                        call.stage != "HALTED"
                        and self.conversations.snapshot(
                            call.interaction_id
                        ).status.value
                        != "CALL_ENDED"
                    ),
                ):
                    await asyncio.wait_for(self.intake_lookup(), timeout=20)
            except Exception:
                self._project(
                    call,
                    "mcp_tool_result",
                    {
                        "tool_name": "get_scheduling_encounter",
                        "tool_call_id": tool_id,
                        "status": "failed",
                        "error_code": "INTAKE_UNAVAILABLE",
                    },
                )
                raise
            self._project(
                call,
                "mcp_tool_result",
                {
                    "tool_name": "get_scheduling_encounter",
                    "tool_call_id": tool_id,
                    "status": "succeeded",
                },
            )
            call.protected = BoundCall(
                INTAKE_CASE if self.caller_resolver is not None else self.approved_case,
                call.room_name,
                call.participant_identity,
                call.expires,
                interaction_id=call.interaction_id,
                require_mcp_identity=call.mcp_scope.private_identity,
                stage="NAME",
            )
            return (
                VERIFICATION_PROMPT
                if os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
                else OPENING
            )
        from veteran_access_bridge.voice.response_policy import constrain_staff_transfer

        spoken, adjusted = constrain_staff_transfer(answer)
        if adjusted:
            self._project(
                call,
                "agent_answered",
                {
                    "text": spoken,
                    "response_policy": "NO_STAFF_TRANSFER_CAPABILITY",
                    "replaces_event_id": event.event_id,
                },
            )
        return spoken

    async def _agent_conversation(self, call, body):
        from veteran_access_bridge.domain import (
            InteractionEventSource,
            InteractionEventType,
        )

        protected = call.protected
        if (
            protected.identity is not None
            and protected.identity.expires_at <= datetime.now(timezone.utc)
            and protected.stage in {"AGENT", "CONFIRM"}
        ):
            if protected.require_mcp_identity:
                # Restart with a fresh three-factor binding.
                call.mcp_scope.matched_case = None
                protected.stage = call.stage = "HALTED"
                protected.identity = None
                return (
                    "Your verification has expired. "
                    "Please start a new call to verify your details."
                )
            protected.identity = None
            protected.verified_first_name = ""
            protected.offer = None
            protected.options = []
            protected.options_sequence = None
            protected.readback_sequence = None
            protected.patient_source_verified = False
            protected.identity_intake = IdentityIntake()
            protected.stage = "NAME"
            return (
                "For your privacy, I need to verify your details again before "
                "continuing. Please say or type your full name and date of birth."
            )
        self._require_agent_identity(call, body)
        if (
            protected.stage == "BOOKED"
            and protected.receipt is not None
            and explicitly_confirms(body.text)
        ):
            return (
                "Your appointment is already confirmed. There is no need to "
                "confirm it again. Is there anything else I can help you with?"
            )
        if protected.stage == "BOOKED" and re.sub(
            r"[^a-z ]", "", body.text.lower()
        ).strip() in {
            "no",
            "no thank you",
            "no thanks",
            "thank you",
            "thanks",
            "goodbye",
            "bye",
        }:
            return (
                "You're welcome. Your appointment is confirmed. "
                f"{self._service_thanks(protected)} "
                "Have a good day."
            )
        if protected.stage == "CONFIRM" and not explicitly_confirms(body.text):
            # A change, question, or refusal invalidates the previous consent referent.
            protected.readback_sequence = None
            protected.offer = None
            protected.stage = "AGENT"
        if not call.mcp_scope.private_identity:
            call.mcp_scope.matched_case = protected.case_id
        call.mcp_scope.workflow_context = {
            "vab_workflow_stage": protected.stage,
            "vab_patient_time_zone": protected.patient_zone,
            "vab_demo_facility": (protected.facility_context or {}).get("name", ""),
            "vab_time_zone_basis": "FACILITY_LOCAL"
            if protected.facility_context
            else "CALLER_SELECTED",
            "vab_patient_source_verified": "true"
            if protected.patient_source_verified
            else "false",
            "vab_scheduling_instruction": (
                (
                    "The patient source was verified in this call; do not repeat "
                    "the patient read. "
                    if protected.patient_source_verified
                    else "Use get_va_patient_health_sandbox_summary before searching. "
                )
                + (
                    "The caller is answering an existing exact readback. On "
                    "affirmative consent use ONLY book_call_appointment; do not "
                    "search or select again. "
                    if protected.stage == "CONFIRM"
                    else ""
                )
                + "Use search_call_appointments for actual options; never invent "
                "slots, providers, or PACT assignment. The host voices the calendar. "
                + (
                    "The caller has already heard the options; use the "
                    "previous search result to select their choice. "
                    "Search again only if preferences changed. "
                    if protected.options
                    else ""
                )
                + "Ask preferences naturally. "
                "Use search_call_knowledge only for a relevant guidance question. "
                "Use select_call_appointment for the caller's choice. The host "
                "will read it back. Only on a later explicit confirmation use "
                "book_call_appointment. Never claim booking without its receipt. "
                "Do not use legacy scheduling tools for this voice workflow."
            ),
        }
        protected.trusted_reply = None
        event = await self.conversations.send_message(
            interaction_id=call.interaction_id,
            message=(
                redact_spoken_identity(
                    body.text.strip(), identity_phase=split_last_four(body.text)[2]
                )
                if os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
                else body.text.strip()
            ),
        )
        if (
            event.event_type != InteractionEventType.AGENT_ANSWERED
            or event.source != InteractionEventSource.WATSONX_ORCHESTRATE
            or event.interaction_id != call.interaction_id
            or event.case_id != INTAKE_CASE
        ):
            raise PermissionError("Verified IBM answer required")
        if protected.trusted_reply:
            return protected.trusted_reply
        answer = event.payload.get("text")
        if not isinstance(answer, str) or not answer.strip():
            raise PermissionError("IBM response contains no speech")
        if answer.strip() == "Skill has stopped processing":
            raise PermissionError("IBM denied the authenticated voice turn")
        # A conversational claim never substitutes for the guarded write receipt.
        if (
            protected.stage == "AGENT"
            and re.search(
                r"\b(openings?|slots?|available|offer"
                r"|appointments?|i have|we have|would .* work)\b",
                answer,
                re.I,
            )
            and re.search(
                r"\b(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)|\d{1,2}:\d{2}"
                r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                answer,
                re.I,
            )
        ):
            return (
                "Which of those times would work for you?"
                if protected.options
                else "What day or time would you like me to check?"
            )
        if re.search(r"\b(booked|confirmed|scheduled|reserved)\b", answer, re.I):
            if protected.stage == "BOOKED" and protected.receipt is not None:
                return (
                    "Your Primary Care appointment is already confirmed for "
                    + local_appointment_time(
                        protected.receipt["begins_at"], protected.patient_zone
                    )
                    + "."
                )
            return "Let's find a time that works for you."
        from veteran_access_bridge.voice.response_policy import constrain_staff_transfer

        return constrain_staff_transfer(answer)[0]

    def _require_agent_identity(self, call, body):
        protected = call.protected
        if (
            not self.agent_scheduling
            or protected is None
            or protected.identity is None
            or not protected.identity.verified
            or protected.identity.case_id != protected.case_id
            or protected.identity.correlation_id != body.voice_session_id
            or protected.identity.expires_at <= datetime.now(timezone.utc)
            or (
                not self.caller_resolver.bound(protected.case_id, body.voice_session_id)
                if self.caller_resolver is not None
                else protected.case_id != self.approved_case
            )
            or (
                call.mcp_scope
                and call.mcp_scope.private_identity
                and call.mcp_scope.matched_case != protected.case_id
            )
            or protected.patient_zone is None
            or protected.stage not in {"AGENT", "CONFIRM", "BOOKED"}
            or call.expires <= time.monotonic()
        ):
            raise PermissionError(
                "Active verified caller and confirmed time zone required"
            )

    async def _agent_tool(self, call, body, name, arguments):
        started = time.perf_counter()
        outcome = "error"
        try:
            result = await self._execute_agent_tool(call, body, name, arguments)
            outcome = "returned"
            return result
        finally:
            logging.getLogger("uvicorn.error.vab_timing").info(
                "Voice MCP operation tool=%s duration_ms=%.1f trace_id=%s outcome=%s",
                name
                if name
                in {
                    "get_va_patient_health_sandbox_summary",
                    "search_call_knowledge",
                    "search_call_appointments",
                    "select_call_appointment",
                    "book_call_appointment",
                }
                else "other",
                (time.perf_counter() - started) * 1000,
                timing_trace_id(),
                outcome,
            )

    async def _execute_agent_tool(self, call, body, name, arguments):
        if name == "verify_synthetic_identity":
            protected = call.protected
            identity = protected.identity if protected else None
            if (
                call.ended
                or not call.mcp_scope.private_identity
                or not identity
                or not identity.verified
                or protected.stage != "VERIFY"
                or identity.case_id != protected.case_id
                or identity.correlation_id != body.voice_session_id
                or identity.expires_at <= datetime.now(timezone.utc)
                or not self.caller_resolver.bound(
                    protected.case_id, body.voice_session_id
                )
                or arguments.get("case_id") != INTAKE_CASE
                or any(
                    arguments.get(k) != "PRIVATE" for k in ("full_name", "birth_date")
                )
            ):
                raise PermissionError("Active privately verified caller required")
            protected.identity_operation = "identity-" + timing_trace_id()
            self._project(
                call,
                "mcp_tool_called",
                {
                    "tool_name": name,
                    "tool_call_id": protected.identity_operation,
                    "status": "started",
                },
            )
            return {"verified": True, "matched_case_id": protected.case_id}
        if os.getenv("VAB_EVAL_READ_ONLY") == "true" and name not in {
            "get_va_patient_health_sandbox_summary",
            "search_call_appointments",
            "search_call_knowledge",
        }:
            raise PermissionError("Evaluation runtime permits scoped reads only")
        if call.ended:
            raise PermissionError("Call has ended")
        self._require_agent_identity(call, body)
        protected = call.protected
        if arguments.get("case_id") != protected.case_id:
            raise PermissionError("Tool must address this verified case")
        if (
            protected.stage == "CONFIRM"
            and explicitly_confirms(body.text)
            and name
            in {
                "get_va_patient_health_sandbox_summary",
                "search_call_appointments",
                "select_call_appointment",
            }
        ):
            # A redundant agent call must not erase the caller's pending choice
            # or reset the prior-turn consent checkpoint.
            return {
                "status": "AWAITING_BOOKING",
                "instruction": (
                    "Use book_call_appointment for the existing selection and "
                    "current caller confirmation. Do not search or select again."
                ),
                "booking_created": False,
            }
        if protected.stage == "BOOKED" and name in {
            "search_call_appointments",
            "select_call_appointment",
            "book_call_appointment",
        }:
            raise PermissionError("This call already has a confirmed appointment")
        if name == "get_va_patient_health_sandbox_summary":
            if self.patient_reader is None and self.caller_resolver is None:
                raise PermissionError("VA sandbox patient reader unavailable")
            if self.caller_resolver is not None:
                result = await run_in_threadpool(
                    self.caller_resolver.read, protected.case_id, body.voice_session_id
                )
            else:
                result = await run_in_threadpool(self.patient_reader, protected.case_id)
            if (
                result.get("case_id") != protected.case_id
                or result.get("identity_matches") is not True
                or result.get("source_verified") is not True
            ):
                raise PermissionError("VA patient identity match required")
            protected.patient_source_verified = True
            return result
        if not protected.patient_source_verified:
            raise PermissionError("Verified VA patient read required first")
        if name == "search_call_knowledge":
            if self.knowledge_reader is None:
                return {
                    "status": "UNAVAILABLE",
                    "results": [],
                    "policy_authority": False,
                }
            return await run_in_threadpool(
                self.knowledge_reader, arguments.get("query", "")
            )
        if name == "search_call_appointments":
            from datetime import date
            from zoneinfo import ZoneInfo

            start = (
                date.fromisoformat(arguments["date_from"])
                if arguments.get("date_from")
                else None
            )
            end = (
                date.fromisoformat(arguments["date_to"])
                if arguments.get("date_to")
                else None
            )
            preference = arguments.get("time_preference", "ANY")
            if (start and end and start > end) or preference not in {
                "ANY",
                "MORNING",
                "AFTERNOON",
            }:
                raise ValueError("Valid appointment preferences required")
            options = await run_in_threadpool(self._offers, protected)

            def matches(option):
                local = option["begins"].astimezone(ZoneInfo(protected.patient_zone))
                return (
                    (start is None or local.date() >= start)
                    and (end is None or local.date() <= end)
                    and (
                        preference == "ANY"
                        or (local.hour < 12) == (preference == "MORNING")
                    )
                )

            previous_options = protected.options
            protected.options = [o for o in options if matches(o)][:3]
            # Searching again invalidates a prior selection and its readback.
            protected.offer = None
            protected.readback_sequence = None
            protected.stage = "AGENT"
            projection = {
                "verified": True,
                "identity_verified": True,
                "booking_case_id": protected.case_id,
                "voice_session_id": body.voice_session_id,
                "patient_time_zone": protected.patient_zone,
                "options": [
                    self._public_option(o, protected) for o in protected.options
                ],
            }
            public = projection["options"]
            unchanged = protected.options_sequence is not None and public == [
                self._public_option(o, protected) for o in previous_options
            ]
            same_turn = protected.options_sequence == body.sequence
            repeat_requested = re.search(
                r"\b(repeat|again|remind me|say those|didn.t catch)\b", body.text, re.I
            )
            if not unchanged:
                self._project(call, "options_presented", projection)
            if not unchanged or not same_turn:
                if not public:
                    protected.trusted_reply = (
                        "I couldn't find an opening for those preferences. "
                        "Would another day or time work?"
                    )
                elif unchanged and not repeat_requested:
                    protected.trusted_reply = "Which of those times would work for you?"
                else:
                    times = [option["local_time"] for option in public]
                    choices = (
                        ", ".join(times[:-1]) + ", or " + times[-1]
                        if len(times) > 1
                        else times[0]
                    )
                    protected.trusted_reply = (
                        f"I have {choices}. Would one of those times work for you?"
                        if len(times) > 1
                        else f"I have {choices}. Would that time work for you?"
                    )
            protected.options_sequence = body.sequence
            return {
                **projection,
                "source": "SUPABASE_TEST_SCHEDULING",
                "synthetic": True,
            }
        if name == "select_call_appointment":
            selected = [
                o
                for o in protected.options
                if o["option_id"] == arguments.get("option_id")
            ]
            if len(selected) != 1:
                raise PermissionError("Choose an option returned in this call")
            protected.offer = selected[0]
            protected.stage = "CONFIRM"
            protected.readback_sequence = body.sequence
            destination = (protected.facility_context or {}).get(
                "name", protected.offer.get("clinic_name")
            )
            protected.trusted_reply = (
                "Just to confirm, you would like Primary Care on "
                + local_appointment_time(
                    protected.offer["begins"], protected.patient_zone
                )
                + (" at " + destination if destination else "")
                + ". Shall I book that appointment?"
            )
            self._project_booking(call)
            return {"status": "AWAITING_CALLER_CONFIRMATION", "booking_created": False}
        if name == "book_call_appointment":
            if (
                protected.stage != "CONFIRM"
                or protected.offer is None
                or protected.readback_sequence is None
                or protected.readback_sequence >= body.sequence
                or not explicitly_confirms(body.text)
            ):
                raise PermissionError(
                    "Current caller confirmation of prior exact readback required"
                )
            canonical = body.model_copy(update={"text": "yes book that appointment"})
            await run_in_threadpool(self._advance, protected, canonical)
            await run_in_threadpool(self._record_booking_note, call)
            self._project_booking(call)
            protected.trusted_reply = (
                "Your Primary Care appointment is confirmed for "
                + local_appointment_time(
                    protected.receipt["begins_at"], protected.patient_zone
                )
                + ". Is there anything else I can help you with?"
            )
            return {
                "status": "BOOKED_SIMULATED",
                "appointment_id": protected.receipt["appointment_id"],
                "verified": True,
            }
        raise PermissionError("Unsupported voice workflow tool")

    @staticmethod
    def _public_option(option, protected):
        return {
            "option_id": option["option_id"],
            "begins_at": option["begins"].isoformat(),
            "ends_at": option["ends"].isoformat(),
            "local_time": local_appointment_time(
                option["begins"], protected.patient_zone
            ),
            "provider_name": option.get("provider_name"),
            "clinic_name": option.get("clinic_name"),
            "facility_name": (protected.facility_context or {}).get("name"),
            "service": "PRIMARY_CARE",
        }

    def _project_scope_receipts(self, call, receipts, prior_events):
        """Join server execution proof only to IBM selections in this exact turn.

        Host intake uses a separate capability and cannot appear in these
        receipts. Raw tool data and bearer capabilities remain private.
        """
        events = self.conversations.events.get_events(call.interaction_id)[
            prior_events:
        ]
        completed = set()
        for receipt in receipts:
            # IBM can omit arguments from its response. Correlate only a unique
            # completed operation and unique selection within this exact grant.
            # The server receipt, never missing/model arguments, proves case scope.
            if sum(r["tool_name"] == receipt["tool_name"] for r in receipts) != 1:
                continue
            matches = []
            for event in events:
                if (
                    event.source.value != "watsonx_orchestrate"
                    or event.event_type.value != "mcp_tool_called"
                ):
                    continue
                payload = event.payload
                name = str(payload.get("tool_name", "")).split(":")[-1]
                arguments = payload.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (ValueError, TypeError):
                        continue
                if (
                    name == receipt["tool_name"]
                    and (
                        arguments is None
                        or (
                            isinstance(arguments, dict)
                            and arguments.get("case_id") == receipt["case_id"]
                        )
                    )
                    and payload.get("tool_call_id")
                ):
                    matches.append(payload["tool_call_id"])
            # Ambiguous or absent IBM provenance must never become an agent claim.
            if len(matches) != 1:
                continue
            completed.add(receipt["tool_name"])
            self._project(
                call,
                "mcp_tool_result",
                {
                    "tool_name": receipt["tool_name"],
                    "tool_call_id": matches[0],
                    **(
                        {
                            "verified": True,
                            "server_operation_id": call.protected.identity_operation,
                        }
                        if receipt["tool_name"] == "verify_synthetic_identity"
                        and call.protected
                        and call.protected.identity_operation
                        else {}
                    ),
                    "status": "succeeded",
                    "invoked_by": "agent",
                    "evidence": "server_scope_receipt",
                    "voice_session_id": call.room_name.removeprefix("vab-"),
                    "scope_verified": True,
                    "verified_case_id": receipt["verified_case_id"],
                    "result": {"verified": receipt["identity_verified"]},
                    **(
                        {
                            "crm_receipt": receipt["crm_receipt"],
                            "voice_session_id": call.room_name.removeprefix("vab-"),
                        }
                        if receipt.get("crm_receipt")
                        else {}
                    ),
                },
            )

        return completed

    def _project(self, call, kind, payload):
        from veteran_access_bridge.domain import (
            InteractionEvent,
            InteractionEventSource,
            InteractionEventType,
        )

        scope = self.conversations.snapshot(call.interaction_id).correlation
        self.conversations.events.append(
            InteractionEvent(
                event_id="evt-" + uuid4().hex[:16],
                event_type=InteractionEventType(kind),
                interaction_id=call.interaction_id,
                case_id=scope.case_id,
                scheduling_encounter_id=scope.scheduling_encounter_id,
                correlation_id=scope.correlation_id,
                source=InteractionEventSource.APPLICATION,
                occurred_at=datetime.now(timezone.utc),
                payload=payload,
            )
        )

    def _record_booking_note(self, call):
        """Best-effort CRM side effect; never roll back or retry a booking."""
        from veteran_access_bridge.services.booking_crm import record_booking_note

        protected = call.protected
        if os.getenv("VAB_ENABLE_CRM") != "true" or protected.crm_note is not None:
            return

        def verify():
            voice = call.room_name.removeprefix("vab-")
            if (
                os.getenv("VAB_ENABLE_CRM") != "true"
                or self.calls.get(voice) is not call
                or call.expires <= time.monotonic()
                or call.stage == "HALTED"
                or protected.stage != "BOOKED"
                or protected.receipt is None
                or protected.identity is None
                or not protected.identity.verified
                or protected.identity.correlation_id != voice
                or self.conversations.snapshot(call.interaction_id).status.value
                == "CALL_ENDED"
            ):
                raise PermissionError("Active verified booking call required")
            request = protected.request
            recovered = self._booking_for(protected).recover(
                request=request,
                assertion=self._assertion(
                    protected.case_id,
                    RECOVERY_SCOPE,
                    case_id=protected.case_id,
                    option_id=request.option_id,
                    slot_id=str(request.slot_id),
                    idempotency_key=request.idempotency_key,
                    voice_session_id=voice,
                ),
            )
            result = _verified_receipt(recovered, protected.case_id)
            if result != protected.receipt:
                raise PermissionError("Independent booking readback changed")
            return result

        protected.crm_note_status = "PENDING"
        try:
            protected.crm_note = record_booking_note(
                case_id=protected.case_id,
                interaction_id=call.interaction_id,
                voice_session_id=call.room_name.removeprefix("vab-"),
                verify=verify,
            )
            protected.crm_note_status = "SAVED"
        except Exception:
            # Ambiguous commit remains pending. A later authenticated turn uses
            # the same appointment-derived key, never resubmits the booking.
            pass

    def _project_booking(self, call):
        protected = call.protected
        if protected.stage == "CONFIRM":
            self._project(
                call,
                "slot_verified",
                {
                    "verified": True,
                    "identity_verified": True,
                    "booking_case_id": protected.case_id,
                    "begins_at": protected.offer["begins"].isoformat(),
                    "ends_at": protected.offer["ends"].isoformat(),
                    "voice_session_id": protected.identity.correlation_id,
                    "patient_time_zone": protected.patient_zone,
                    "clinic_name": protected.offer.get("clinic_name"),
                    "facility_name": (protected.facility_context or {}).get("name"),
                    "provider_name": protected.offer.get("provider_name"),
                },
            )
        elif protected.stage == "BOOKED" and protected.receipt is not None:
            receipt = protected.receipt
            self._project(
                call,
                "simulated_booking_recorded",
                {
                    "verified": True,
                    "identity_verified": True,
                    "booking_case_id": protected.case_id,
                    "appointment_id": receipt["appointment_id"],
                    "begins_at": receipt["begins_at"].isoformat(),
                    "ends_at": receipt["ends_at"].isoformat(),
                    "voice_session_id": receipt["voice_session_id"],
                    "state": "BOOKED_SIMULATED",
                    "clinic_name": receipt.get("clinic_name"),
                    "facility_name": (protected.facility_context or {}).get("name"),
                    "provider_name": receipt.get("provider_name"),
                    "patient_time_zone": protected.patient_zone,
                    "crm_note_status": protected.crm_note_status,
                    **(
                        {"crm_note_id": protected.crm_note["record_id"]}
                        if protected.crm_note is not None
                        else {}
                    ),
                },
            )

    def _offer(self, call):
        offers = self._offers(call)
        if offers:
            return offers[0]
        raise NoVerifiedAppointment(
            "No independently verified case-bound appointment is available"
        )

    def _offers(self, call):
        with self.read_connect() as conn:
            with conn.cursor() as cur:
                if (
                    assert_synthetic_scheduling_database(cur, conn, write=False)
                    != "vab_test"
                ):
                    raise PermissionError("Synthetic database required")
                cur.execute(
                    "SELECT s.slot_id,d.provenance->'slot_bindings'->(s.slo"
                    "t_id::text)->>'option_id',"
                    "s.begins_at,s.ends_at,c.name,"
                    "c.rules->'provider_names'->>s.provider_id,c.clinic_id "
                    "FROM vab_test.slot s JOIN vab_test.clinic c "
                    "ON c.clinic_id=s.clinic_id "
                    "JOIN vab_te"
                    "st.data_source d ON d.source_id=s.source_id "
                    "WHERE s.status='AVAILABLE' AND s.begins_at>clock_timestamp() "
                    "AND d.provenance->'slot_bindings'->(s.slot_id::text)->"
                    ">'case_id'=%s "
                    "ORDER BY s.begins_at,s.slot_id LIMIT 10",
                    (call.case_id,),
                )
                candidates = cur.fetchall()
        offers = []
        for (
            slot_id,
            option_id,
            begins,
            ends,
            clinic_name,
            provider_name,
            clinic_id,
        ) in candidates:
            if (
                call.facility_context
                and clinic_id != call.facility_context["clinic_id"]
            ):
                continue
            if not option_id:
                continue
            try:
                if self.agent_scheduling and self.slot_refresher is not None:
                    self.slot_refresher(call.identity, slot_id, option_id)
                source = verified_consent_evidence(
                    self.read_connect,
                    binding=call.identity,
                    option_id=option_id,
                    slot_id=slot_id,
                    host_subject=self.subject,
                    voice_session_id=call.identity.correlation_id,
                    identity_verification_id=str(call.identity.event_id),
                )
            except PermissionError:
                continue
            offers.append(
                {
                    "slot_id": slot_id,
                    "option_id": option_id,
                    "begins": begins,
                    "ends": ends,
                    "source": source,
                    "clinic_name": clinic_name,
                    "clinic_id": clinic_id,
                    "provider_name": provider_name,
                }
            )
        return offers

    @staticmethod
    def _service_thanks(call):
        name = (
            call.verified_first_name if call.identity and call.identity.verified else ""
        )
        return "Thank you for your service" + (f", {name}." if name else ".")

    def _identity_reply(self, call):
        if configured_facilities():
            return self._begin_facility_selection(call)
        call.stage = "TIMEZONE"
        return (
            f"{self._service_thanks(call)} Your identity is verified. "
            "Which time zone should I "
            "use for your appointment times—for example, Pacific, Mountain, "
            "Central, or Eastern?"
        )

    def _begin_facility_selection(self, call):
        """A caller choice confirms destination, never identity or booking consent."""
        offers = self._offers(call)
        clinics = {o.get("clinic_id") for o in offers}
        if len(clinics) != 1 or None in clinics:
            raise NoVerifiedAppointment("One mapped case-bound clinic required")
        call.facility_context = resolve_demo_facility(clinics.pop())
        call.stage = "FACILITY"
        return (
            f"{self._service_thanks(call)} Your identity is verified. "
            f"Would you like to schedule at {call.facility_context['name']}?"
        )

    def _advance(self, call, body):
        if call.ended:
            raise PermissionError("Call has ended")
        if body.action == "opening":
            if call.stage != "NEW" or body.text:
                raise PermissionError("Opening cannot reset call state")
            call.stage = "NAME"
            return (
                VERIFICATION_PROMPT
                if os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
                else OPENING
            )
        text = body.text.strip()
        if not text:
            raise ValueError("Final speech is required")
        private_check = os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") == "true"
        spoken_check = os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
        if body.action == "last_four" and (
            not private_check or call.stage != "LAST_FOUR"
        ):
            raise PermissionError("Private identity input is not expected")
        clean = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
        if self.agent_scheduling and call.stage in {
            "NAME",
            "DOB",
            "IDENTITY_CONFIRM",
            "LAST_FOUR",
        }:
            if call.identity_intake is None:
                call.identity_intake = IdentityIntake()
            intake = call.identity_intake
            last_four = None
            if call.stage == "LAST_FOUR":
                if spoken_check:
                    _, last_four, _ = split_last_four(text)
                    if last_four is None:
                        intake.turns += 1
                        if intake.turns > 10:
                            call.stage = "HALTED"
                            return intake.stop()
                        return (
                            "Sorry, I didn't catch those last four digits. Could "
                            "you say them one digit at a time?"
                        )
                    ready, reply = True, ""
                elif body.action != "last_four":
                    return (
                        "Please enter the four digits in the private field, "
                        "rather than saying them aloud."
                    )
                elif not re.fullmatch(r"[0-9]{4}", text):
                    raise PermissionError("Invalid private identity input")
                elif not spoken_check:
                    last_four = text
                ready, reply = True, ""
            else:
                if spoken_check:
                    # A paused four-digit birth year is still part of DOB, not
                    # the extra factor. Preserve the existing date continuation.
                    birth_continuation = intake.pending_birth and spoken_birth_date(
                        intake.pending_birth + " " + text
                    )
                    if birth_continuation:
                        digits, attempted = None, False
                    else:
                        text, digits, attempted = split_last_four(text)
                    if attempted:
                        intake.last_four = digits or ""
                    if not text:
                        text = (
                            f"{intake.name}, {intake.birth_date}"
                            if intake.name and intake.birth_date
                            else intake.name
                        )
                reply, ready = intake.receive(text)
                if spoken_check:
                    last_four = intake.last_four or None
                if ready and private_check:
                    if self.caller_resolver is None:
                        raise PermissionError("Additional identity source unavailable")
                    if not spoken_check or last_four is None:
                        call.stage = "LAST_FOUR"
                        if spoken_check:
                            return (
                                "Please say the last four digits of your social, "
                                "one digit at a time."
                            )
                        return (
                            "Please enter the last four digits of your test Social "
                            "Security number in the private field on your screen. "
                            "Do not say them aloud."
                        )
            if not ready:
                call.stage = (
                    "HALTED"
                    if intake.halted
                    else (
                        "IDENTITY_CONFIRM" if intake.awaiting_confirmation else "NAME"
                    )
                )
                return reply
            try:
                if self.caller_resolver is not None and call.case_booking is None:
                    case = self.caller_resolver.resolve(
                        name=intake.name,
                        birth_date=intake.birth_date,
                        **({"last_four": last_four} if private_check else {}),
                        voice=body.voice_session_id,
                        assertion=self._assertion(
                            self.caller_resolver.case_id(body.voice_session_id),
                            CASE_PROVISION_SCOPE,
                        ),
                    )
                    if case is None:
                        reply = intake.mismatch()
                        call.stage = "HALTED" if intake.halted else "NAME"
                        return reply
                    call.case_id = case
                    call.case_booking = self.booking_factory(case)
                identity = verify_and_record_synthetic_identity(
                    self.connect,
                    self.authenticator,
                    assertion=self._assertion(call.case_id, IDENTITY_SCOPE),
                    case_id=call.case_id,
                    full_name=intake.name,
                    birth_date=intake.birth_date,
                    correlation_id=body.voice_session_id,
                )
            except Exception:
                intake.clear()
                raise
            if not identity.verified:
                call.identity = None
                reply = intake.mismatch()
                call.stage = "HALTED" if intake.halted else "NAME"
                return reply
            call.verified_first_name = (intake.name or "").split()[0].title()
            intake.clear()
            call.identity = identity
            if call.require_mcp_identity:
                call.stage = "VERIFY"
                return ""
            return self._identity_reply(call)
        if call.stage == "NAME":
            name = spoken_name(text)
            if name is None:
                return (
                    "Please spell your full name using letters or the phonet"
                    "ic alphabet, and say space between names."
                )
            call.name = name
            call.stage = "DOB"
            return (
                "Please say your date of birth, including the month, da"
                "y, and four digit year."
            )
        if call.stage == "DOB":
            dob = spoken_birth_date(text)
            if dob is None:
                return "Please repeat your birth date, for example January 15, 1980."
            call.identity = verify_and_record_synthetic_identity(
                self.connect,
                self.authenticator,
                assertion=self._assertion(call.case_id, IDENTITY_SCOPE),
                case_id=call.case_id,
                full_name=call.name,
                birth_date=dob,
                correlation_id=body.voice_session_id,
            )
            call.name = ""
            if not call.identity.verified:
                call.stage = "HALTED"
                return (
                    "I could not verify the synthetic identity. No appointm"
                    "ent was booked. Please contact the test operator."
                )
            if self.agent_scheduling:
                if configured_facilities():
                    return self._begin_facility_selection(call)
                call.stage = "TIMEZONE"
                return (
                    "Thank you. Which time zone should I use for your appointment "
                    "times—for example, Pacific, Mountain, Central, or Eastern?"
                )
            try:
                call.offer = self._offer(call)
            except NoVerifiedAppointment:
                call.stage = "HALTED"
                return (
                    "Your identity is verified, but I do not have a currently "
                    "verified appointment to offer. No appointment has been booked. "
                    "Please contact the scheduling team."
                )
            call.stage = "CONFIRM"
            begins = (
                call.offer["begins"]
                .astimezone(timezone.utc)
                .strftime("%B %d, %Y at %H:%M UTC")
            )
            ends = call.offer["ends"].astimezone(timezone.utc).strftime("%H:%M UTC")
            return (
                "Your synthetic identity is verified. "
                f"I can book Primary Care on {begins}, ending at {ends}. "
                "To confirm this specific appointment, say yes, book th"
                "at appointment. To decline, say no."
            )
        if call.stage == "FACILITY" and self.agent_scheduling:
            if clean in {
                "no",
                "no thank you",
                "different facility",
                "another facility",
            }:
                call.stage = "HALTED"
                return (
                    "I do not have verified availability for another facility in "
                    "this call. Please contact the scheduling team for that location. "
                    "No appointment has been booked."
                )
            if not explicitly_confirms(text):
                return (
                    f"Would you like to use {call.facility_context['name']}? "
                    "Please say yes, or ask for another facility."
                )
            if call.identity is None or call.identity.expires_at <= datetime.now(
                timezone.utc
            ):
                raise PermissionError("Current verified identity required")
            # Legacy wire field denotes display time, not patient residence.
            call.patient_zone = call.facility_context["time_zone"]
            call.stage = "AGENT"
            return (
                "I'll use the facility's local time for your appointment. "
                "Are you looking for a routine follow-up, and what days or times "
                "work best for you?"
            )
        if call.stage == "TIMEZONE" and self.agent_scheduling:
            zone = spoken_zone(text)
            if zone is None:
                return "Please say your time zone, for example Central time."
            call.patient_zone = zone
            call.stage = "AGENT"
            return (
                "Thank you. Are you looking for a routine follow-up, "
                "and what days or times work best for you?"
            )
        if call.stage == "CONFIRM":
            if clean in {"no", "no thank you", "cancel", "do not book", "dont book"}:
                call.stage = "DECLINED"
                return "Understood. No appointment was booked."
            if clean != "yes book that appointment":
                return (
                    "I have not booked anything. To confirm the appointment"
                    " I just offered, say yes, book that appointment, or sa"
                    "y no."
                )
            if call.identity.expires_at <= datetime.now(timezone.utc):
                raise PermissionError("Identity expired before consent")
            offer = call.offer
            if self.agent_scheduling and self.slot_refresher is not None:
                self.slot_refresher(call.identity, offer["slot_id"], offer["option_id"])
            source = verified_consent_evidence(
                self.read_connect,
                binding=call.identity,
                option_id=offer["option_id"],
                slot_id=offer["slot_id"],
                host_subject=self.subject,
                voice_session_id=call.identity.correlation_id,
                identity_verification_id=str(call.identity.event_id),
            )
            actor = "synthetic-voice:" + body.voice_session_id
            now = int(time.time())
            decision_token = jwt.encode(
                {
                    "iss": DECISION_ISSUER,
                    "aud": DECISION_AUDIENCE,
                    "sub": actor,
                    "role": "VETERAN",
                    "case_id": call.case_id,
                    "synthetic": True,
                    "iat": now,
                    "exp": now + 30,
                },
                self.decision_secret,
                algorithm="HS256",
            )
            consent = (
                self.gateway.record_internal_va_veteran_response_from_trusted_service(
                    assertion=decision_token,
                    expected_actor_id=actor,
                    case_id=call.case_id,
                    option_id=offer["option_id"],
                    idempotency_key="voice-consent:" + body.voice_session_id,
                    correlation_id=body.voice_session_id,
                    verified_evidence_reference=source,
                    accepted=True,
                )
            )
            if consent.status != "ACCEPTED":
                raise PermissionError("Explicit consent was not persisted")
            call.request = VABookingRequest(
                call.case_id,
                offer["option_id"],
                offer["slot_id"],
                "voice-book:" + body.voice_session_id,
            )
            bound = dict(
                case_id=call.case_id,
                option_id=offer["option_id"],
                slot_id=str(offer["slot_id"]),
                idempotency_key=call.request.idempotency_key,
                voice_session_id=body.voice_session_id,
            )
            call.stage = "COMMITTING"
            try:
                receipt = self._booking_for(call).book(
                    request=call.request,
                    assertion=self._assertion(
                        call.case_id,
                        SCOPE,
                        **bound,
                        identity_verification_id=str(call.identity.event_id),
                        veteran_confirmation_id=str(consent.decision_id),
                        consent_response="CONFIRMED",
                        consent_expires_at=now + 240,
                    ),
                )
            except Exception:
                # Never resubmit after an ambiguous write.
                # Recover only by independent readback.
                receipt = self._booking_for(call).recover(
                    request=call.request,
                    assertion=self._assertion(call.case_id, RECOVERY_SCOPE, **bound),
                )
            result = _verified_receipt(receipt, call.case_id)
            if result.get("voice_session_id") != body.voice_session_id:
                raise PermissionError("Verified receipt must identify this call")
            call.receipt = result
            call.stage = "BOOKED"
            return (
                "Your synthetic Primary Care appointment is booked and "
                "independently verified. This completes the test call."
            )
        if call.stage == "BOOKED":
            return (
                "Your synthetic appointment is already verified. I will"
                " not create another booking."
            )
        raise PermissionError("Call cannot accept further scheduling actions")


async def live_participant(room_name, identity):
    from livekit import api

    async with api.LiveKitAPI() as client:
        return await client.room.get_participant(
            api.RoomParticipantIdentity(room=room_name, identity=identity)
        )


def build_trusted_voice_booking(*, conversations=None):
    dynamic = os.getenv("VAB_ENABLE_DYNAMIC_SANDBOX_CALLERS") == "true"
    if dynamic and (
        os.getenv("VAB_ENABLE_AGENT_SCHEDULING") != "true"
        or os.getenv("VAB_ENABLE_BROWSER_PC_BOOKING") != "true"
        or conversations is None
    ):
        raise PermissionError(
            "Dynamic callers require authenticated IBM browser intake"
        )
    if conversations is not None:
        from veteran_access_bridge.services.orchestrate_runtime import (
            HttpOrchestrateRuntime,
        )

        if not isinstance(conversations.runtime, HttpOrchestrateRuntime):
            raise PermissionError("Real IBM runtime required for browser intake")
    if os.getenv("VAB_SUPABASE_TEST_MODE") != "true" or (
        not dynamic
        and not re.fullmatch(
            r"VAB-DEMO-20261113-CASE-\d{3}",
            os.getenv("VAB_PRIVATE_PC_APPROVED_CASE", ""),
        )
    ):
        raise PermissionError(
            "Explicit approved synthetic voice configuration required"
        )
    from veteran_access_bridge.services.protected_host_keys import (
        private_voice_key,
        public_host_key,
    )

    private = private_voice_key()
    public = serialization.load_pem_public_key(public_host_key().encode("ascii"))
    if public.public_numbers() != private.public_key().public_numbers():
        raise PermissionError("Host keypair mismatch")
    decision_secret = os.environ["VAB_SIGNED_DECISION_VERIFIER_SECRET"]
    from veteran_access_bridge.app.browser_primary_care import read_intake_via_mcp
    from veteran_access_bridge.services.call_knowledge import search_call_knowledge
    from veteran_access_bridge.services.call_patient_lookup import read_patient_summary
    from veteran_access_bridge.services.call_slot_verification import (
        verify_test_inventory,
    )
    from veteran_access_bridge.services.sandbox_callers import SandboxCallerResolver

    authenticator = TrustedHostAuthenticator.from_environment(
        connect_private_supabase_test_scheduling
    )

    async def lookup():
        return await read_intake_via_mcp(
            os.environ["VAB_TRUSTED_HOST_ISSUER"], os.environ["VAB_MCP_API_KEY"]
        )

    return TrustedVoiceBooking(
        worker_secret=os.environ["VAB_VOICE_WORKER_SECRET"],
        issuer=os.environ["VAB_TRUSTED_HOST_ISSUER"],
        audience=os.environ["VAB_TRUSTED_HOST_AUDIENCE"],
        subject=os.environ["VAB_TRUSTED_HOST_SUBJECT"],
        private_key=private,
        authenticator=authenticator,
        booking=build_private_booking_from_environment(),
        gateway=PrivateSyntheticSchedulingGateway(
            connect=connect_private_supabase_test_scheduling,
            verifier_secret=decision_secret,
        ),
        decision_secret=decision_secret,
        connect=connect_private_supabase_test_scheduling,
        read_connect=connect_private_supabase_test_scheduling_readonly,
        participant_lookup=live_participant,
        conversations=conversations,
        approved_case=os.getenv("VAB_PRIVATE_PC_APPROVED_CASE", APPROVED_CASE),
        browser_booking=os.getenv("VAB_ENABLE_BROWSER_PC_BOOKING") == "true",
        intake_lookup=lookup,
        agent_scheduling=os.getenv("VAB_ENABLE_AGENT_SCHEDULING") == "true",
        patient_reader=lambda case: read_patient_summary(
            connect_private_supabase_test_scheduling_readonly, case
        ),
        knowledge_reader=search_call_knowledge,
        slot_refresher=lambda identity, slot, option: verify_test_inventory(
            connect_private_supabase_test_scheduling,
            identity=identity,
            slot_id=slot,
            option_id=option,
            host_subject=os.environ["VAB_TRUSTED_HOST_SUBJECT"],
        ),
        caller_resolver=(
            SandboxCallerResolver(
                connect_private_supabase_test_scheduling,
                connect_private_supabase_test_scheduling_readonly,
                authenticator,
            )
            if dynamic
            else None
        ),
        booking_factory=lambda case: build_private_booking_from_environment(
            approved_case=case
        ),
    )


def create_trusted_voice_router(service):
    router = APIRouter()

    @router.post("/internal/synthetic-primary-care/voice-turn", include_in_schema=False)
    async def turn(body: VoiceTurn, request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Trusted voice worker required")
        try:
            return await service.handle(body, token)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(403, "Voice action not authorized") from exc
        except Exception as exc:
            raise HTTPException(
                503, "Voice action unverified; operator review required"
            ) from exc

    return router
