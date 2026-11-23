/* eslint-disable prettier/prettier -- Screen A feature branch: run Prettier at integration/release gate. */
import { describe, expect, it } from "vitest";
import { screenAEvidence } from "@/components/msa/screen-a-evidence";
import { printableLetterHtml, type ConfirmedSyntheticBooking } from "@/components/msa/screen-a-after-call";
import type { MonitorEvent } from "@/lib/live-monitor";
import type { ExecutionStep } from "@/lib/mcp-execution";

const event = (type: string): MonitorEvent => ({
  event_id: "e-" + type,
  event_type: type,
  source: "vab",
  occurred_at: "2026-11-10T21:00:00Z",
  correlation_id: "corr-synthetic",
});

const step = (tool: string, status: ExecutionStep["status"]): ExecutionStep => ({
  id: tool,
  tool,
  status,
  category: "read",
  provenance: "authoritative",
  source: "watsonx_orchestrate",
  startedAt: "2026-11-10T21:00:00Z",
  eventIds: [tool],
});

describe("Screen A evidence-led autonomous operation", () => {
  it("never claims a booked slot from an agent answer or a connected LiveKit room", () => {
    const result = screenAEvidence("live", true, [event("agent_answered")], [], false);
    expect(result.mediaConnected).toBe(true);
    expect(result.conversationReady).toBe(true);
    expect(result.scheduling.at(-1)?.state).toBe("pending");
    expect(result.scheduling[1]?.state).toBe("pending");
    expect(result.intake[1]?.state).toBe("complete");
    expect(result.intake[7]?.state).toBe("pending");
  });

  it("requires explicit verified=true; a successfully completed tool can reject the caller", () => {
    const tool = step("verify_synthetic_identity", "succeeded");
    const rejected: MonitorEvent = {
      ...event("mcp_tool_result"),
      tool_name: "verify_synthetic_identity",
      status: "completed",
      verified: false,
    };
    const verified: MonitorEvent = { ...rejected, invoked_by: "agent", verified: true };
    expect(screenAEvidence("live", false, [], [tool], false).identityVerified).toBe(false);
    expect(screenAEvidence("live", false, [rejected], [tool], false).identityVerified).toBe(false);
    expect(screenAEvidence("live", false, [verified], [tool], false).identityVerified).toBe(true);
    expect(
      screenAEvidence(
        "live",
        false,
        [{ ...verified, status: "failed", error_code: "IDENTITY_ERROR" }],
        [tool],
        false,
      ).identityVerified,
    ).toBe(false);
    expect(
      screenAEvidence(
        "live",
        false,
        [{ ...verified, tool_name: "search_availability" }],
        [tool],
        false,
      ).identityVerified,
    ).toBe(false);
    expect(
      screenAEvidence(
        "live",
        false,
        [verified, { ...rejected, event_id: "newer-denial" }],
        [tool],
        false,
      ).identityVerified,
    ).toBe(false);
    expect(
      screenAEvidence(
        "live",
        false,
        [{ ...verified, status: undefined }],
        [tool],
        false,
      ).identityVerified,
    ).toBe(true);
  });

  it("keeps selection, consent and booking pending until governed receipts exist", () => {
    const steps = [
      step("verify_synthetic_identity", "succeeded"),
      step("search_availability", "succeeded"),
      step("record_option_selection", "succeeded"),
      step("record_veteran_confirmation", "succeeded"),
    ];
    const verified: MonitorEvent = {
      ...event("mcp_tool_result"),
      tool_name: "verify_synthetic_identity",
      status: "completed",
      invoked_by: "agent",
      verified: true,
    };
    const result = screenAEvidence(
      "ready",
      false,
      [event("intake_completed"), verified],
      steps,
      true,
    );
    expect(result.identityVerified).toBe(true);
    expect(result.scheduling[0]?.state).toBe("complete");
    expect(result.scheduling[1]?.state).toBe("complete");
    expect(result.scheduling[2]?.state).toBe("complete");
    expect(result.scheduling[3]?.state).toBe("pending");
    expect(result.scheduling[4]?.state).toBe("pending");
    expect(result.scheduling[5]?.state).toBe("pending");
    expect(result.intake[7]?.state).toBe("pending");
  });

  it("does not invent after-call completion when a caller hangs up", () => {
    const result = screenAEvidence("ready", false, [], [], true);
    expect(result.intake[7]?.state).toBe("pending");
    expect(result.intake[6]?.state).toBe("pending");
  });
});

describe("confirmation letter is synthetic and sanitized", () => {
  it("prints only a provided verified synthetic booking and escapes untrusted fields", () => {
    const booking: ConfirmedSyntheticBooking = {
      synthetic: true,
      verifiedReadback: true,
      veteranName: "<script>alert('x')</script>",
      careType: "Primary care",
      facility: "Synthetic VA Clinic",
      appointmentDate: "2026-11-18",
      localTimeAndZone: "10:00 AM CST",
      visitType: "In person",
      confirmationReference: "SIM-TEST-001",
    };
    const html = printableLetterHtml(booking);
    expect(html).toContain("SANDBOX DOCUMENT");
    expect(html).toContain("SIM-TEST-001");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>alert('x')</script>");
  });
});
