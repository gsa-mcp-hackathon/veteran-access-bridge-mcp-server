import { describe, expect, it } from "vitest";
import { projectCallerActivityPage } from "@/lib/caller-activity-projection";
import { parseDemoCallAction } from "@/lib/demo-call-gateway";

const scope = {
  voiceSessionId: "voice_123",
  interactionId: "interaction_123",
  caseId: "DEMO-PC-VOICE-INTAKE-001",
  correlationId: "corr_123",
};
const event = {
  synthetic: true,
  event_id: "evt-1",
  event_type: "mcp_tool_result",
  source: "watsonx_orchestrate",
  occurred_at: "2026-11-11T06:00:00+00:00",
  case_id: scope.caseId,
  interaction_id: scope.interactionId,
  correlation_id: scope.correlationId,
  scheduling_encounter_id: "SE_001",
  payload: {
    tool_name: "verify_synthetic_identity",
    tool_call_id: "call_123",
    status: "completed",
    result: { patient_name: "DO_NOT_LEAK" },
    arguments: { birth_date: "DO_NOT_LEAK" },
  },
};
const page = {
  synthetic: true,
  voice_session_id: scope.voiceSessionId,
  interaction_id: scope.interactionId,
  case_id: scope.caseId,
  correlation_id: scope.correlationId,
  scheduling_encounter_id: "SE_001",
  status: "AGENT_HANDLING",
  human_control_mode: "AUTONOMOUS",
  events: [event],
  next_cursor: "evt-1",
  raw_sql: "DO_NOT_LEAK",
  private_transcript: "DO_NOT_LEAK",
};

describe("guest caller operational event declassification", () => {
  it("returns only scope-bound, minimal and synthetic metadata", () => {
    const result = projectCallerActivityPage(page, scope);
    expect(result).not.toBeNull();
    expect(result?.events).toHaveLength(1);
    expect(result?.events[0]?.payload).toEqual({
      tool_name: "verify_synthetic_identity",
      tool_call_id: "call_123",
      status: "completed",
    });
    expect(JSON.stringify(result)).not.toContain("DO_NOT_LEAK");
    expect(result?.voice_session_id).toBe(scope.voiceSessionId);
  });

  it("preserves only a literal identity result boolean and never a completed-only guess", () => {
    const denied = projectCallerActivityPage(
      { ...page, events: [{ ...event, payload: { ...event.payload, verified: false } }] },
      scope,
    );
    expect(denied?.events[0]?.payload).toMatchObject({
      tool_name: "verify_synthetic_identity",
      status: "completed",
      verified: false,
    });
    const accepted = projectCallerActivityPage(
      { ...page, events: [{ ...event, payload: { ...event.payload, verified: true } }] },
      scope,
    );
    expect(accepted?.events[0]?.payload).toMatchObject({ verified: true });
    const invalid = projectCallerActivityPage(
      { ...page, events: [{ ...event, payload: { ...event.payload, verified: "true" } }] },
      scope,
    );
    expect(invalid?.events[0]?.payload).not.toHaveProperty("verified");
    const wrongTool = projectCallerActivityPage(
      {
        ...page,
        events: [
          {
            ...event,
            payload: { ...event.payload, tool_name: "search_availability", verified: true },
          },
        ],
      },
      scope,
    );
    expect(wrongTool?.events[0]?.payload).not.toHaveProperty("verified");
    expect(JSON.stringify(denied)).not.toContain("DO_NOT_LEAK");
  });

  it("rejects wrong voice session, case, interaction, correlation, event scope", () => {
    expect(projectCallerActivityPage({ ...page, voice_session_id: "other" }, scope)).toBeNull();
    expect(projectCallerActivityPage({ ...page, case_id: "OTHER_CASE" }, scope)).toBeNull();
    expect(projectCallerActivityPage({ ...page, interaction_id: "other" }, scope)).toBeNull();
    expect(projectCallerActivityPage({ ...page, correlation_id: "other" }, scope)).toBeNull();
    expect(
      projectCallerActivityPage({ ...page, events: [{ ...event, case_id: "OTHER_CASE" }] }, scope),
    ).toBeNull();
    expect(
      projectCallerActivityPage({ ...page, events: [{ ...event, synthetic: false }] }, scope),
    ).toBeNull();
  });

  it("rejects unexpected event types, malformed cursors and oversized pages", () => {
    expect(
      projectCallerActivityPage({ ...page, events: [{ ...event, event_type: "unknown" }] }, scope),
    ).toBeNull();
    expect(projectCallerActivityPage({ ...page, next_cursor: "<script>" }, scope)).toBeNull();
    expect(
      projectCallerActivityPage({ ...page, events: Array(101).fill(event) }, scope),
    ).toBeNull();
    expect(projectCallerActivityPage({ ...page, synthetic: false }, scope)).toBeNull();
  });

  it("sanitizes speech and does not construct a transcript", () => {
    const result = projectCallerActivityPage(
      {
        ...page,
        events: [{ ...event, event_type: "veteran_utterance", payload: { text: "DO_NOT_LEAK" } }],
      },
      scope,
    );
    expect(result?.events[0]?.payload).toEqual({ transcript_available: false });
  });
});

describe("guest activity action validation", () => {
  it("requires a valid backend-owned voice session and optional opaque cursor", () => {
    expect(parseDemoCallAction({ action: "activity", voice_session_id: "voice_123" })).toEqual({
      action: "activity",
      voice_session_id: "voice_123",
    });
    expect(
      parseDemoCallAction({ action: "activity", voice_session_id: "voice_123", cursor: "evt-1" }),
    ).toEqual({ action: "activity", voice_session_id: "voice_123", cursor: "evt-1" });
    expect(
      parseDemoCallAction({ action: "activity", voice_session_id: "../../../etc" }),
    ).toBeNull();
    expect(
      parseDemoCallAction({ action: "activity", voice_session_id: "voice_123", cursor: "<x>" }),
    ).toBeNull();
  });
});
