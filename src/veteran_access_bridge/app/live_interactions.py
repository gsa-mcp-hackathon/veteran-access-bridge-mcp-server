"""Application-controlled live interaction service for the MSA workspace.

Issue #81.

This service owns the synthetic interaction transport/projection layer. It
coordinates the correlation registry, Orchestrate runtime abstraction, and
append-only InteractionEventStore without becoming a scheduling state machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from veteran_access_bridge.domain import (
    CorrelationRegistry,
    HumanControlMode,
    InteractionChannel,
    InteractionCorrelation,
    InteractionEvent,
    InteractionEventSource,
    InteractionEventType,
    build_agent_opening_instruction,
)
from veteran_access_bridge.domain.avery_script import (
    build_unselected_incoming_call_instruction,
)
from veteran_access_bridge.mcp.cases import load_demo_facility_name
from veteran_access_bridge.services.interaction_events import InteractionEventStore
from veteran_access_bridge.services.orchestrate_runtime import (
    FakeOrchestrateRuntime,
    HttpOrchestrateRuntime,
    OrchestrateAuthenticationError,
    OrchestrateConfig,
    OrchestrateProtocolError,
    OrchestrateRuntime,
    OrchestrateRuntimeError,
    OrchestrateTimeoutError,
    OrchestrateUnavailableError,
    RuntimeInteraction,
)


class LiveInteractionStatus(StrEnum):
    INCOMING_CALL = "INCOMING_CALL"
    AGENT_HANDLING = "AGENT_HANDLING"
    ATTENTION_RECOMMENDED = "ATTENTION_RECOMMENDED"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"
    MSA_JOINED = "MSA_JOINED"
    CALL_ENDED = "CALL_ENDED"


class MsaInteractionAction(StrEnum):
    MONITOR = "MONITOR"
    JOIN = "JOIN"
    ACCEPT_HANDOFF = "ACCEPT_HANDOFF"
    END = "END"


@dataclass(frozen=True)
class LiveInteractionSnapshot:
    correlation: InteractionCorrelation
    runtime_interaction: RuntimeInteraction | None
    event_count: int
    status: LiveInteractionStatus
    human_control_mode: HumanControlMode
    runtime_failure_code: str | None = None


class LiveInteractionService:
    """Synthetic interaction coordinator used by the application API."""

    def __init__(
        self,
        *,
        runtime: OrchestrateRuntime | None = None,
        correlation_registry: CorrelationRegistry | None = None,
        event_store: InteractionEventStore | None = None,
    ) -> None:
        self.runtime = runtime or _runtime_from_environment()
        self.correlations = correlation_registry or CorrelationRegistry()
        self.events = event_store or InteractionEventStore()
        self._runtime_interactions: dict[str, RuntimeInteraction] = {}
        self._human_control: dict[str, HumanControlMode] = {}
        self._runtime_failures: dict[str, str] = {}

    @staticmethod
    def _runtime_message(
        correlation: InteractionCorrelation,
        message: str,
        *,
        message_label: str = "Veteran utterance",
    ) -> str:
        """Attach application-owned correlation context for the agent runtime.

        These identifiers are already known to Veteran Access Bridge and must not
        be requested from the Veteran. The agent may use them to call governed
        tools, but should not echo them back unless the MSA explicitly asks.
        """

        if correlation.case_id == "DEMO-PC-VOICE-INTAKE-001":
            from veteran_access_bridge.mcp.session_scope import runtime_context

            context = runtime_context()
            stage = context.get("vab_workflow_stage")
            if stage == "VERIFY":
                return (
                    "The trusted voice service has collected the private factors. "
                    "Call verify_synthetic_identity using the registered case_id and "
                    "session_scope. Supply PRIVATE for both full_name and birth_date. "
                    "Do not request or send personal details or call other tools."
                )
            handoff = ""
            if context.get("vab_identity_verified") == "true" and stage in {
                "AGENT",
                "CONFIRM",
                "BOOKED",
            }:
                # These intake turns are handled by the trusted voice host and
                # are therefore absent from IBM's dialogue history. Summarize
                # that transition from the active server scope, never caller text.
                # The summary grants no authority; tools still enforce the scope.
                handoff = (
                    "[CURRENT VOICE HOST HANDOFF]\n"
                    "The voice host has completed caller identity verification "
                    "and collected the patient's time zone. Those steps happened "
                    "outside this dialogue history. Do not ask for name, date of "
                    "birth, or time zone again. Earlier intake prompts are stale. "
                    f"The current workflow stage is {stage}. "
                    "Use the current registered application context and your "
                    "attached tools to address the latest caller request. This "
                    "summary is not booking consent or a booking receipt.\n"
                    "[END CURRENT VOICE HOST HANDOFF]\n\n"
                )
            # The correlation remains an intake record after identity matches.
            # Repeating that stale case in each user message competes with the
            # current server-owned context supplied separately to Orchestrate.
            return (
                handoff
                + "Continue the existing call using registered application context "
                "variables for current identity and case scope. Conversation "
                "history does not reset those values. Keep responses concise.\n\n"
                + message_label
                + ":\n"
                + message
            )

        try:
            facility_name = load_demo_facility_name(correlation.case_id)
        except ValueError:
            facility_name = None

        return (
            "[APPLICATION CONTEXT - INTERNAL, DO NOT ASK THE VETERAN TO PROVIDE "
            "OR REPEAT THESE IDENTIFIERS]\n"
            f"case_id: {correlation.case_id}\n"
            f"scheduling_encounter_id: {correlation.scheduling_encounter_id}\n"
            f"channel: {correlation.channel.value}\n"
            f"facility_name: {facility_name or 'VA Medical Center'}\n"
            "[END APPLICATION CONTEXT]\n\n"
            "[CONVERSATION INSTRUCTIONS - INTERNAL]\n"
            "Continue the existing call; do not restart the opening greeting.\n"
            + (
                "Follow the agent's identity and case-scope policy using registered "
                "application context variables. This message does not establish "
                "identity or tool authority.\n"
                if correlation.case_id == "DEMO-PC-VOICE-INTAKE-001"
                else "If identity verification is needed, ask for last name, last4, "
                "and date of birth.\n"
            )
            + "Keep most responses concise (1-3 sentences) "
            "unless details are required.\n"
            "Wait for the Veteran turn to complete before responding.\n"
            "[END CONVERSATION INSTRUCTIONS]\n\n" + message_label + ":\n" + message
        )

    @staticmethod
    def _runtime_failure_code(exc: OrchestrateRuntimeError) -> str:
        if isinstance(exc, OrchestrateAuthenticationError):
            return "ORCHESTRATE_AUTHENTICATION"
        if isinstance(exc, OrchestrateTimeoutError):
            return "ORCHESTRATE_TIMEOUT"
        if isinstance(exc, OrchestrateUnavailableError):
            return "ORCHESTRATE_UNAVAILABLE"
        if isinstance(exc, OrchestrateProtocolError):
            return "ORCHESTRATE_PROTOCOL"
        return "ORCHESTRATE_FAILURE"

    def _runtime_failure_event(
        self,
        *,
        correlation: InteractionCorrelation,
        exc: OrchestrateRuntimeError,
    ) -> InteractionEvent:
        code = self._runtime_failure_code(exc)
        self._runtime_failures[correlation.interaction_id] = code
        event = InteractionEvent(
            event_id=f"evt-{uuid4().hex[:16]}",
            event_type=InteractionEventType.HUMAN_ATTENTION_RECOMMENDED,
            interaction_id=correlation.interaction_id,
            case_id=correlation.case_id,
            scheduling_encounter_id=correlation.scheduling_encounter_id,
            correlation_id=correlation.correlation_id,
            source=InteractionEventSource.APPLICATION,
            occurred_at=datetime.now(timezone.utc),
            payload={
                "failure_code": code,
                "recoverable": True,
                "state_preserved": True,
            },
        )
        self.events.append(event)
        return event

    async def create_interaction(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        channel: InteractionChannel,
        initial_message: str | None = None,
        agent_opening: bool = False,
        invoke_runtime: bool = True,
    ) -> LiveInteractionSnapshot:
        interaction_id = f"int-{uuid4().hex[:16]}"
        correlation_id = f"corr-{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)

        self.correlations.register(
            InteractionCorrelation(
                interaction_id=interaction_id,
                case_id=case_id,
                scheduling_encounter_id=scheduling_encounter_id,
                correlation_id=correlation_id,
                channel=channel,
                created_at=now,
            )
        )
        self.events.append(
            InteractionEvent(
                event_id=f"evt-{uuid4().hex[:16]}",
                event_type=InteractionEventType.INTERACTION_RECEIVED,
                interaction_id=interaction_id,
                case_id=case_id,
                scheduling_encounter_id=scheduling_encounter_id,
                correlation_id=correlation_id,
                source=InteractionEventSource.APPLICATION,
                occurred_at=now,
                payload={
                    "channel": channel.value,
                    "runtime_owner": (
                        "bridge_runtime" if invoke_runtime else "embedded_orchestrate"
                    ),
                },
            )
        )

        if not invoke_runtime:
            return self.snapshot(interaction_id)

        opening_message = initial_message
        capture_as_veteran_utterance = True
        if agent_opening and not (initial_message and initial_message.strip()):
            opening_message = (
                build_unselected_incoming_call_instruction()
                if case_id == "DEMO-PC-VOICE-INTAKE-001"
                else build_agent_opening_instruction()
            )
            capture_as_veteran_utterance = False

        if opening_message and opening_message.strip():
            correlation = self.correlations.require(interaction_id)
            if capture_as_veteran_utterance:
                self._capture_conversation_events(
                    correlation=correlation,
                    message=opening_message,
                )
                runtime_message = self._runtime_message(correlation, opening_message)
            else:
                runtime_message = self._runtime_message(
                    correlation,
                    opening_message,
                    message_label="Application event",
                )
            try:
                runtime_interaction = await self.runtime.start_interaction(
                    interaction_id=interaction_id,
                    message=runtime_message,
                )
            except OrchestrateRuntimeError as exc:
                self._runtime_failure_event(
                    correlation=self.correlations.require(interaction_id),
                    exc=exc,
                )
                return self.snapshot(interaction_id)

            self._runtime_interactions[interaction_id] = runtime_interaction
            self._append_runtime_tool_activity(
                correlation=self.correlations.require(interaction_id),
                activity=runtime_interaction.tool_activity,
            )
            if runtime_interaction.run_id:
                self.correlations.attach_runtime(
                    interaction_id,
                    orchestrate_run_id=runtime_interaction.run_id,
                    orchestrate_session_id=runtime_interaction.session_id,
                )
            self.events.append(
                InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=InteractionEventType.AGENT_ANSWERED,
                    interaction_id=interaction_id,
                    case_id=case_id,
                    scheduling_encounter_id=scheduling_encounter_id,
                    correlation_id=correlation_id,
                    source=InteractionEventSource.WATSONX_ORCHESTRATE,
                    occurred_at=datetime.now(timezone.utc),
                    payload={
                        "runtime_started": True,
                        "run_id": runtime_interaction.run_id,
                        "text": runtime_interaction.initial_response_text or "",
                    },
                )
            )

        return self.snapshot(interaction_id)

    async def send_message(
        self,
        *,
        interaction_id: str,
        message: str,
        _application_event: bool = False,
    ) -> InteractionEvent:
        if not message.strip():
            raise ValueError("message is required.")

        correlation = self.correlations.require(interaction_id)
        if not _application_event:
            self._capture_conversation_events(
                correlation=correlation,
                message=message,
            )
        runtime_message = self._runtime_message(
            correlation,
            message,
            message_label="Application event"
            if _application_event
            else "Veteran utterance",
        )
        runtime_interaction = self._runtime_interactions.get(interaction_id)
        try:
            if runtime_interaction is None:
                runtime_interaction = await self.runtime.start_interaction(
                    interaction_id=interaction_id,
                    message=runtime_message,
                    session_id=correlation.orchestrate_session_id,
                )
                self._runtime_interactions[interaction_id] = runtime_interaction
            else:
                runtime_event = await self.runtime.send_message(
                    interaction=runtime_interaction,
                    message=runtime_message,
                )
                if (
                    runtime_event.run_id
                    and runtime_event.run_id != correlation.orchestrate_run_id
                ):
                    correlation = self.correlations.attach_runtime(
                        interaction_id,
                        orchestrate_run_id=runtime_event.run_id,
                        orchestrate_session_id=runtime_event.session_id,
                    )
                self._runtime_failures.pop(interaction_id, None)
                self._append_runtime_tool_activity(
                    correlation=correlation,
                    activity=runtime_event.payload.get("tool_activity", ()),
                )
                event = InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=InteractionEventType.AGENT_ANSWERED,
                    interaction_id=interaction_id,
                    case_id=correlation.case_id,
                    scheduling_encounter_id=correlation.scheduling_encounter_id,
                    correlation_id=correlation.correlation_id,
                    source=InteractionEventSource.WATSONX_ORCHESTRATE,
                    occurred_at=datetime.now(timezone.utc),
                    payload={
                        "text": runtime_event.payload.get("text", ""),
                        "runtime_event_type": runtime_event.event_type.value,
                        "run_id": runtime_event.run_id,
                    },
                )
                self.events.append(event)
                return event
        except OrchestrateRuntimeError as exc:
            return self._runtime_failure_event(
                correlation=correlation,
                exc=exc,
            )

        self._append_runtime_tool_activity(
            correlation=correlation,
            activity=runtime_interaction.tool_activity,
        )

        if runtime_interaction.run_id:
            correlation = self.correlations.attach_runtime(
                interaction_id,
                orchestrate_run_id=runtime_interaction.run_id,
                orchestrate_session_id=runtime_interaction.session_id,
            )

        event = InteractionEvent(
            event_id=f"evt-{uuid4().hex[:16]}",
            event_type=InteractionEventType.AGENT_ANSWERED,
            interaction_id=interaction_id,
            case_id=correlation.case_id,
            scheduling_encounter_id=correlation.scheduling_encounter_id,
            correlation_id=correlation.correlation_id,
            source=InteractionEventSource.WATSONX_ORCHESTRATE,
            occurred_at=datetime.now(timezone.utc),
            payload={
                "runtime_started": True,
                "run_id": runtime_interaction.run_id,
                "text": runtime_interaction.initial_response_text or "",
            },
        )
        self.events.append(event)
        return event

    def record_embedded_message(
        self,
        *,
        interaction_id: str,
        direction: str,
        text: str,
        thread_id: str | None = None,
    ) -> InteractionEvent:
        """Project an observed embedded-chat message without invoking Orchestrate.

        The embedded IBM channel is the conversational runtime. This method only
        mirrors observable text into the MSA event stream so the Bridge does not
        create a duplicate agent turn.
        """

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text is required.")

        normalized_direction = direction.strip().lower()
        if normalized_direction not in {"user", "assistant"}:
            raise ValueError("direction must be 'user' or 'assistant'.")

        correlation = self.correlations.require(interaction_id)
        payload: dict[str, object] = {
            "text": clean_text,
            "embedded_channel": True,
        }
        if thread_id:
            payload["thread_id"] = thread_id[:256]

        if normalized_direction == "user":
            event_type = InteractionEventType.VETERAN_UTTERANCE
            source = InteractionEventSource.CONVERSATION
            self._capture_conversation_events(
                correlation=correlation,
                message=clean_text,
            )
        else:
            event_type = InteractionEventType.AGENT_ANSWERED
            source = InteractionEventSource.WATSONX_ORCHESTRATE

        event = InteractionEvent(
            event_id=f"evt-{uuid4().hex[:16]}",
            event_type=event_type,
            interaction_id=interaction_id,
            case_id=correlation.case_id,
            scheduling_encounter_id=correlation.scheduling_encounter_id,
            correlation_id=correlation.correlation_id,
            source=source,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
        self.events.append(event)
        return event

    def _capture_conversation_events(
        self,
        *,
        correlation: InteractionCorrelation,
        message: str,
    ) -> None:
        lower = message.lower()
        captures: list[tuple[InteractionEventType, dict[str, str]]] = []

        if "primary care" in lower:
            captures.append(
                (
                    InteractionEventType.INTENT_CAPTURED,
                    {
                        "care_category": "PRIMARY_CARE",
                        "request_intent": "SCHEDULE_PRIMARY_CARE",
                    },
                )
            )

        if "morning" in lower:
            captures.append(
                (
                    InteractionEventType.PREFERENCE_CAPTURED,
                    {"preferred_time_of_day": "MORNING"},
                )
            )
        elif "afternoon" in lower:
            captures.append(
                (
                    InteractionEventType.PREFERENCE_CAPTURED,
                    {"preferred_time_of_day": "AFTERNOON"},
                )
            )

        for event_type, payload in captures:
            self.events.append(
                InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=event_type,
                    interaction_id=correlation.interaction_id,
                    case_id=correlation.case_id,
                    scheduling_encounter_id=correlation.scheduling_encounter_id,
                    correlation_id=correlation.correlation_id,
                    source=InteractionEventSource.CONVERSATION,
                    occurred_at=datetime.now(timezone.utc),
                    payload=payload,
                )
            )

    def record_external_failure(
        self,
        *,
        interaction_id: str,
        failure_code: str,
        tool_outcome: str | None = None,
    ) -> InteractionEvent:
        """Record an explicitly reported downstream failure without inferring it.

        This hook is for approved normalized runtime/tool events such as an
        explicit MCP outage. It deliberately rejects arbitrary failure labels.
        """

        allowed = {
            "MCP_UNAVAILABLE",
            "DETERMINISTIC_SERVICE_FAILURE",
            "EVENT_STREAM_DISCONNECT",
        }
        if failure_code not in allowed:
            raise ValueError("Unsupported external failure code.")

        correlation = self.correlations.require(interaction_id)
        self._runtime_failures[interaction_id] = failure_code
        payload: dict[str, object] = {
            "failure_code": failure_code,
            "recoverable": True,
            "state_preserved": True,
        }
        if tool_outcome is not None:
            payload["tool_outcome"] = tool_outcome

        event = InteractionEvent(
            event_id=f"evt-{uuid4().hex[:16]}",
            event_type=InteractionEventType.HUMAN_ATTENTION_RECOMMENDED,
            interaction_id=interaction_id,
            case_id=correlation.case_id,
            scheduling_encounter_id=correlation.scheduling_encounter_id,
            correlation_id=correlation.correlation_id,
            source=InteractionEventSource.APPLICATION,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
        self.events.append(event)
        return event

    def _append_runtime_tool_activity(self, *, correlation, activity) -> None:
        for item in activity or ():
            if not isinstance(item, dict):
                continue
            phase = str(item.get("phase") or "").lower()
            name = str(item.get("name") or "tool")
            if phase == "result":
                event_type = InteractionEventType.MCP_TOOL_RESULT
                payload = {
                    "tool_name": name,
                    "result": item.get("result"),
                    "tool_call_id": item.get("tool_call_id"),
                    "status": item.get("status"),
                    "evidence": "watsonx_orchestrate_response",
                }
            else:
                event_type = InteractionEventType.MCP_TOOL_CALLED
                payload = {
                    "tool_name": name,
                    "arguments": item.get("arguments"),
                    "tool_call_id": item.get("tool_call_id"),
                    "evidence": "watsonx_orchestrate_response",
                }
            self.events.append(
                InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=event_type,
                    interaction_id=correlation.interaction_id,
                    case_id=correlation.case_id,
                    scheduling_encounter_id=correlation.scheduling_encounter_id,
                    correlation_id=correlation.correlation_id,
                    source=InteractionEventSource.WATSONX_ORCHESTRATE,
                    occurred_at=datetime.now(timezone.utc),
                    payload=payload,
                )
            )

    def append_grounded_agent_explanation(
        self,
        *,
        interaction_id: str,
        text: str,
        evidence_type: str,
    ) -> InteractionEvent:
        correlation = self.correlations.require(interaction_id)
        event = InteractionEvent(
            event_id=f"evt-{uuid4().hex[:16]}",
            event_type=InteractionEventType.AGENT_ANSWERED,
            interaction_id=interaction_id,
            case_id=correlation.case_id,
            scheduling_encounter_id=correlation.scheduling_encounter_id,
            correlation_id=correlation.correlation_id,
            source=InteractionEventSource.WATSONX_ORCHESTRATE,
            occurred_at=datetime.now(timezone.utc),
            payload={
                "text": text,
                "grounded_by": evidence_type,
                "synthetic": True,
            },
        )
        self.events.append(event)
        return event

    def record_msa_action(
        self,
        *,
        interaction_id: str,
        action: MsaInteractionAction,
    ) -> LiveInteractionSnapshot:
        correlation = self.correlations.require(interaction_id)
        now = datetime.now(timezone.utc)

        if self._status(interaction_id) is LiveInteractionStatus.CALL_ENDED:
            raise ValueError("Interaction already ended.")
        if action in {MsaInteractionAction.JOIN, MsaInteractionAction.ACCEPT_HANDOFF}:
            if self._status(interaction_id) not in {
                LiveInteractionStatus.HANDOFF_REQUIRED,
                LiveInteractionStatus.ATTENTION_RECOMMENDED,
            }:
                raise ValueError("Avery has not requested human assistance.")
        if action is MsaInteractionAction.MONITOR:
            self._human_control[interaction_id] = HumanControlMode.MSA_MONITORING
        elif action in {
            MsaInteractionAction.JOIN,
            MsaInteractionAction.ACCEPT_HANDOFF,
        }:
            self._human_control[interaction_id] = HumanControlMode.MSA_JOINED
            self.events.append(
                InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=InteractionEventType.MSA_JOINED,
                    interaction_id=interaction_id,
                    case_id=correlation.case_id,
                    scheduling_encounter_id=correlation.scheduling_encounter_id,
                    correlation_id=correlation.correlation_id,
                    source=InteractionEventSource.MSA,
                    occurred_at=now,
                    payload={"action": action.value, "context_retained": True},
                )
            )
        elif action is MsaInteractionAction.END:
            self.events.append(
                InteractionEvent(
                    event_id=f"evt-{uuid4().hex[:16]}",
                    event_type=InteractionEventType.INTERACTION_ENDED,
                    interaction_id=interaction_id,
                    case_id=correlation.case_id,
                    scheduling_encounter_id=correlation.scheduling_encounter_id,
                    correlation_id=correlation.correlation_id,
                    source=InteractionEventSource.MSA,
                    occurred_at=now,
                    payload={"action": action.value},
                )
            )
        return self.snapshot(interaction_id)

    def _status(self, interaction_id: str) -> LiveInteractionStatus:
        status = LiveInteractionStatus.INCOMING_CALL
        for event in self.events.get_events(interaction_id):
            if event.event_type is InteractionEventType.AGENT_ANSWERED:
                status = LiveInteractionStatus.AGENT_HANDLING
            elif event.event_type is InteractionEventType.HUMAN_ATTENTION_RECOMMENDED:
                status = LiveInteractionStatus.ATTENTION_RECOMMENDED
            elif event.event_type is InteractionEventType.TRANSFER_REQUESTED:
                status = LiveInteractionStatus.HANDOFF_REQUIRED
            elif event.event_type is InteractionEventType.MSA_JOINED:
                status = LiveInteractionStatus.MSA_JOINED
            elif event.event_type is InteractionEventType.INTERACTION_ENDED:
                status = LiveInteractionStatus.CALL_ENDED
        return status

    def snapshot(self, interaction_id: str) -> LiveInteractionSnapshot:
        correlation = self.correlations.require(interaction_id)
        return LiveInteractionSnapshot(
            correlation=correlation,
            runtime_interaction=self._runtime_interactions.get(interaction_id),
            event_count=len(self.events.get_events(interaction_id)),
            status=self._status(interaction_id),
            human_control_mode=self._human_control.get(
                interaction_id,
                HumanControlMode.AGENT_HANDLING,
            ),
            runtime_failure_code=self._runtime_failures.get(interaction_id),
        )


def _runtime_from_environment() -> OrchestrateRuntime:
    mode = os.getenv("ORCHESTRATE_RUNTIME_MODE", "fake").strip().lower()
    if mode == "remote":
        return HttpOrchestrateRuntime(OrchestrateConfig.from_env())
    if mode != "fake":
        raise ValueError("ORCHESTRATE_RUNTIME_MODE must be 'fake' or 'remote'.")
    return FakeOrchestrateRuntime()
