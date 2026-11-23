import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  businessDays,
  calendarFromSlots,
  categorize,
  coverage,
  parseVerifiedAvailability,
  stepsFromMonitor,
  stepsFromReplay,
  TOOL_REGISTRY,
} from "@/lib/mcp-execution";
import { BASE_SLOTS, emptyEncounter, scriptFor, slotsFor } from "@/lib/scenario";
import {
  LiveConversation,
  MiniCalendar,
  StatusPill,
  TRANSCRIPT_UNAVAILABLE,
} from "@/components/msa/command-center";
import type { MonitorEvent } from "@/lib/live-monitor";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
  ClientOnly: ({ fallback }: { fallback: React.ReactNode }) => <>{fallback}</>,
}));
beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("tool registry categories", () => {
  it("classifies read, write and unknown tools", () => {
    for (const t of [
      "get_scheduling_encounter",
      "search_availability",
      "validate_booking_preconditions",
      "assess_access_standard",
    ])
      expect(categorize(t)).toBe("read");
    expect(categorize("record_option_selection")).toBe("write");
    expect(categorize("record_veteran_confirmation")).toBe("write");
    expect(categorize("delete_everything")).toBe("other");
    expect(categorize(undefined)).toBe("other");
  });
  it("never reports a completed dataset call without a real dataset event", () => {
    const steps = stepsFromReplay(
      scriptFor("success").flatMap((s) =>
        s.kind === "event" ? [{ ...s.ev, status: "completed" as const }] : [],
      ),
    );
    expect(steps.some((s) => s.category === "dataset")).toBe(false);
    expect(coverage(steps).dataset).toBe("implemented");
    expect(coverage(steps).read).toBe("observed");
  });
});

describe("authoritative steps", () => {
  const ev = (o: Partial<MonitorEvent>): MonitorEvent => ({
    event_id: "e",
    event_type: "mcp_tool_called",
    source: "mcp",
    occurred_at: "2026-11-09T10:00:00Z",
    correlation_id: "c",
    ...o,
  });
  it("keeps identity pending until the server links the operation and the IBM selection", () => {
    const tool = { tool_name: "verify_synthetic_identity" };
    const started = ev({ ...tool, tool_call_id: "operation", source: "application" });
    const selection = ev({ ...tool, tool_call_id: "ibm" });
    const returned = ev({
      ...tool,
      event_type: "mcp_tool_result",
      tool_call_id: "ibm",
      status: "succeeded",
    });
    expect(stepsFromMonitor([started])[0]?.status).toBe("running");
    expect(stepsFromMonitor([selection, returned])[0]?.status).toBe("result_received");
    const proof = ev({
      ...returned,
      source: "application",
      invoked_by: "agent",
      server_operation_id: "operation",
      verified: true,
    });
    const result = stepsFromMonitor([started, selection, returned, proof]);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ status: "succeeded", invokedBy: "agent" });
  });
  it("groups called/result, measures duration and maps status", () => {
    const steps = stepsFromMonitor([
      ev({ event_id: "a", tool_name: "search_availability", tool_call_id: "t1" }),
      ev({
        event_id: "b",
        event_type: "mcp_tool_result",
        tool_call_id: "t1",
        status: "success",
        occurred_at: "2026-11-09T10:00:01.250Z",
      }),
      ev({ event_id: "c", tool_name: "mystery", tool_call_id: "t2" }),
      ev({ event_id: "d", event_type: "session_state", tool_call_id: "t3" }),
    ]);
    expect(steps).toHaveLength(2);
    expect(steps[0]).toMatchObject({ status: "succeeded", durationMs: 1250, category: "read" });
    expect(steps[1]).toMatchObject({ status: "running", category: "other" });
    expect(steps[1]!.durationMs).toBeUndefined();
  });
});

describe("canonical contract hardening", () => {
  const ev = (o: Partial<MonitorEvent>): MonitorEvent => ({
    event_id: "e",
    event_type: "mcp_tool_result",
    source: "mcp",
    occurred_at: "2026-11-09T10:00:02Z",
    correlation_id: "c",
    ...o,
  });
  it("registry matches canonical membership and omits book_appointment", () => {
    expect(Object.keys(TOOL_REGISTRY).sort()).toEqual(
      [
        "get_va_patient_health_sandbox_summary",
        "search_call_appointments",
        "select_call_appointment",
        "book_call_appointment",
        "search_call_knowledge",
        "assess_access_standard",
        "get_crm_case",
        "record_crm_interaction",
        "create_crm_follow_up",
        "update_crm_follow_up",
        "get_scheduling_encounter",
        "record_option_selection",
        "record_veteran_confirmation",
        "search_availability",
        "validate_booking_preconditions",
        "verify_caller_identity",
        "verify_synthetic_identity",
      ].sort(),
    );
    expect(categorize("book_appointment")).toBe("other");
    expect(categorize("record_option_selection")).toBe("write");
  });
  it("replay simulated booking is not projected as an MCP step", () => {
    const steps = stepsFromReplay(
      scriptFor("success").flatMap((s) =>
        s.kind === "event" ? [{ ...s.ev, status: "completed" as const }] : [],
      ),
    );
    expect(steps.some((s) => /simulate_book|book_appointment/.test(s.tool))).toBe(false);
    expect(steps.every((s) => s.provenance === "replay")).toBe(true);
  });
  it("result without status is result_received, not success", () => {
    const [s] = stepsFromMonitor([
      ev({ event_id: "r1", tool_name: "search_availability", tool_call_id: "t1" }),
    ]);
    expect(s!.status).toBe("result_received");
    expect(stepsFromMonitor([ev({ tool_call_id: "t1", status: "success" })])[0]!.status).toBe(
      "succeeded",
    );
    expect(stepsFromMonitor([ev({ tool_call_id: "t1", status: "blocked" })])[0]!.status).toBe(
      "blocked",
    );
  });
  it("unlinked result is not paired and has no inferred duration", () => {
    const steps = stepsFromMonitor([
      ev({
        event_id: "a",
        event_type: "mcp_tool_called",
        tool_name: "search_availability",
        occurred_at: "2026-11-09T10:00:00Z",
      }),
      ev({ event_id: "b", tool_name: "search_availability", status: "success" }),
    ]);
    expect(steps).toHaveLength(2);
    expect(steps[1]).toMatchObject({ id: "b", status: "succeeded", eventIds: ["b"] });
    expect(steps[1]!.durationMs).toBeUndefined();
    expect(steps[0]!.status).toBe("running");
  });
  it("status pill labels result_received neutrally", () => {
    render(<StatusPill status="result_received" />);
    expect(screen.getByText("Result received · outcome unverified")).toBeInTheDocument();
  });
});

describe("five business day calendar", () => {
  it("skips weekends and is relative to the reference date", () => {
    const days = businessDays(new Date(2026, 10, 13)); // Friday
    expect(days.map((d) => d.getDay())).toEqual([1, 2, 3, 4, 5]);
    expect(days[0]!.getDate()).toBe(16);
  });
  it("renders weekday/date, selected chip and +N more from slotsFor fixture", () => {
    const enc = {
      ...emptyEncounter(),
      verified: true,
      slotsLoaded: true,
      evaluated: true,
      selectedId: "s1",
    };
    const slots = slotsFor(enc);
    const from = new Date(2026, 10, 9);
    expect(calendarFromSlots(slots, from)[0]!.slots).toHaveLength(2);
    render(<MiniCalendar slots={slots} from={from} />);
    expect(screen.getByLabelText(/Tue Nov 10 08:30, selected option/)).toBeInTheDocument();
    expect(screen.getByText("Selection recorded — not a booking.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 more times on Tue/ }));
    expect(screen.getByRole("region", { name: "Alternative times" })).toHaveTextContent("13:00");
    expect(screen.queryByText(/Booking confirmed/)).toBeNull();
  });
  it("leaks no slots on identity mismatch", () => {
    expect(slotsFor({ ...emptyEncounter(), slotsLoaded: true, evaluated: true })).toEqual([]);
    expect(BASE_SLOTS.length).toBeGreaterThan(0);
  });
});

describe("conversation provenance", () => {
  it("authoritative mode shows unavailable transcript and no speech", () => {
    render(
      <LiveConversation
        authoritative
        messages={[{ id: "m", speaker: "veteran", time: "1", text: "SECRET" }]}
        steps={[]}
        slots={[]}
        showCalendar
        calendarFrom={new Date()}
        onFocusStep={() => {}}
        emptyLabel="Awaiting MCP events"
      />,
    );
    expect(screen.getByText(TRANSCRIPT_UNAVAILABLE)).toBeInTheDocument();
    expect(screen.getByText("Awaiting authorized availability evidence")).toBeInTheDocument();
    expect(screen.queryByText("SECRET")).toBeNull();
  });
  it("availability adapter rejects unscoped or unverified evidence", () => {
    const ok = {
      kind: "verified_availability_summary",
      verified: true,
      synthetic: true,
      case_id: "c",
      correlation_id: "k",
      slots: [{ date: "2026-11-10", time: "08:30" }],
    };
    expect(parseVerifiedAvailability(ok, { case_id: "c", correlation_id: "k" })).not.toBeNull();
    expect(parseVerifiedAvailability(ok, { case_id: "x", correlation_id: "k" })).toBeNull();
    expect(
      parseVerifiedAvailability({ ...ok, verified: false }, { case_id: "c", correlation_id: "k" }),
    ).toBeNull();
    expect(parseVerifiedAvailability(ok, { case_id: "c", correlation_id: null })).toBeNull();
  });
  it("never auto-advances scripted activity; replay requires deliberate opt-in", async () => {
    vi.useFakeTimers();
    const { MSAAppShell } = await import("@/components/msa/app-shell");
    render(<MSAAppShell />);
    expect(screen.getByText(/SANDBOX · Live observer · LiveKit not connected/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Five business day/ })).toBeNull();
    for (let i = 0; i < 18; i++)
      await act(async () => {
        vi.advanceTimersByTime(1800);
      });
    expect(screen.queryByRole("region", { name: /Five business day/ })).toBeNull();
    expect(screen.queryByText(/Simulated booking complete/)).toBeNull();

    fireEvent.click(screen.getByText("Advanced · developer scripted replay (not live)"));
    fireEvent.click(screen.getByRole("button", { name: "Start scripted replay (demo only)" }));
    expect(
      screen.getByText(/Explicit scripted replay · NO LiveKit audio connection/),
    ).toBeInTheDocument();
    for (let i = 0; i < 18; i++)
      await act(async () => {
        vi.advanceTimersByTime(1800);
      });
    expect(screen.getByRole("region", { name: /Five business day/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "MCP Execution Inspector" })).toHaveTextContent(
      "Implemented · not run",
    );

    fireEvent.click(screen.getByRole("button", { name: "Return to live observer" }));
    expect(screen.getByText(/SANDBOX · Live observer · LiveKit not connected/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Five business day/ })).toBeNull();
  });
});
