import type { CallPhase } from "./use-one-click-call";
import { friendlyToolName } from "@/lib/avery-tool-labels";
import type { MonitorEvent } from "@/lib/live-monitor";
import type { ExecutionStep } from "@/lib/mcp-execution";

/**
 * Screen A consumes canonical, sanitized events only. A media connection, a
 * spoken choice, or an MCP result without an explicit success status is NOT
 * a completed booking, identity verification, delivery or staff transfer.
 */
export type WorkflowState = "complete" | "active" | "pending" | "blocked";
export type WorkflowStage = {
  id: string;
  label: string;
  state: WorkflowState;
  explanation: string;
};

export const INTAKE_STAGES = [
  "Call Start",
  "AI Answers Instantly",
  "Identify Intent",
  "Structured Intake",
  "Validation & Logic",
  "Scheduling Options",
  "Notifications & Logging",
  "Call Completion",
] as const;

export const SCHEDULING_STAGES = [
  "Intake",
  "Verify",
  "Search",
  "Select",
  "Confirm",
  "Book",
] as const;

function matchesSuccessfulTool(steps: ExecutionStep[], ...names: string[]) {
  return steps.some((step) => names.includes(step.tool) && step.status === "succeeded");
}
function observed(events: MonitorEvent[], ...types: string[]) {
  return events.some((event) => types.includes(event.event_type));
}

export function screenAEvidence(
  phase: CallPhase,
  agentAudio: boolean,
  events: MonitorEvent[],
  steps: ExecutionStep[],
  ended: boolean,
): {
  intake: WorkflowStage[];
  scheduling: WorkflowStage[];
  identityVerified: boolean;
  toolObserved: boolean;
  intentObserved: boolean;
  mediaConnected: boolean;
  conversationReady: boolean;
} {
  const connected = phase === "live";
  const callCreated = connected || ended || steps.length > 0 || events.length > 0;
  // A completed tool invocation can still return verified=false. Advance
  // ONLY for an explicit true outcome from the canonical identity tool.
  const latestIdentityResult = events
    .filter(
      (event) =>
        event.event_type === "mcp_tool_result" && event.tool_name === "verify_synthetic_identity",
    )
    .at(-1);
  const identityVerified =
    events.some(
      (event) => event.event_type === "voice_identity_verified" && event.source === "application",
    ) ||
    events.some((event) => event.appointment_options?.identity_verified === true) ||
    events.some((event) => event.voice_booking?.identity_verified === true) ||
    (latestIdentityResult?.verified === true &&
      latestIdentityResult.invoked_by === "agent" &&
      !latestIdentityResult.error_code &&
      !["blocked", "denied", "failed", "error", "timeout", "rejected"].includes(
        (latestIdentityResult.status ?? "").toLowerCase(),
      ));
  const protectedProof = events
    .map((event) => event.voice_booking)
    .filter(Boolean)
    .at(-1);
  const searchObserved = !!protectedProof || matchesSuccessfulTool(steps, "search_availability");
  // Only a validated protected receipt establishes selection and consent.
  const selectionRecorded = protectedProof?.state === "BOOKED_SIMULATED";
  const consentRecorded = selectionRecorded;
  // Spoken booking claims and arbitrary completed tool calls remain insufficient.
  const bookingReadBack = protectedProof?.state === "BOOKED_SIMULATED";
  const intentObserved = observed(events, "intent_captured");
  const intakeObserved = observed(events, "intake_completed", "structured_intake_completed");
  const afterCallObserved = observed(events, "after_call_work_completed");
  const completed = observed(events, "call_completed");
  const escalated = observed(events, "escalation_required", "handoff_requested");

  const schedulingDone = [
    intakeObserved,
    identityVerified,
    searchObserved,
    selectionRecorded,
    consentRecorded,
    bookingReadBack,
  ];
  const scheduling: WorkflowStage[] = SCHEDULING_STAGES.map((label, index) => ({
    id: label.toLowerCase(),
    label,
    state: schedulingDone[index] ? "complete" : index === 0 && callCreated ? "active" : "pending",
    explanation:
      index === 5
        ? "Requires persisted synthetic booking read-back."
        : index === 4
          ? "Requires a governed record of the Veteran's explicit verbal consent."
          : index === 3
            ? "A spoken preference is not a persisted selection."
            : "Advances only on a corresponding backend event.",
  }));
  const markers = [
    callCreated,
    agentAudio,
    intentObserved,
    intakeObserved,
    identityVerified,
    searchObserved,
    afterCallObserved,
    completed,
  ];
  const intake: WorkflowStage[] = INTAKE_STAGES.map((label, index) => ({
    id: String(index + 1),
    label,
    state: markers[index]
      ? "complete"
      : escalated && index > 1
        ? "blocked"
        : index === 0 && phase === "starting"
          ? "active"
          : index === 1 && connected && !agentAudio
            ? "active"
            : "pending",
    explanation:
      index === 1
        ? "Requires actual Avery audio in the LiveKit room."
        : index === 7
          ? "A local hang-up alone is not a backend call-completion receipt."
          : "Derived from media state and authoritative events.",
  }));
  return {
    intake,
    scheduling,
    identityVerified,
    toolObserved: steps.length > 0,
    intentObserved,
    mediaConnected: connected,
    conversationReady: connected && agentAudio,
  };
}

/** Avoid showing opaque event types as if they were patient dialog. */
export function eventLabel(event: MonitorEvent) {
  if (event.event_type === "mcp_tool_called")
    return event.tool_name ? `Started · ${friendlyToolName(event.tool_name)}` : "MCP tool called";
  if (event.event_type === "mcp_tool_result")
    return event.tool_name
      ? `Result received · ${friendlyToolName(event.tool_name)}`
      : "MCP tool result received";
  return event.event_type.replaceAll("_", " ");
}
