import { describe, expect, it } from "vitest";
import { AVERY_TOOL_LABELS, friendlyToolActivity, friendlyToolName } from "@/lib/avery-tool-labels";

describe("Avery tool presentation aliases", () => {
  it("retains the legacy labels and includes guarded voice workflow labels", () => {
    expect(Object.keys(AVERY_TOOL_LABELS)).toHaveLength(25);
    for (const name of [
      "search_call_appointments",
      "select_call_appointment",
      "book_call_appointment",
      "search_call_knowledge",
    ])
      expect(AVERY_TOOL_LABELS[name]?.label).toBeTruthy();
  });

  it("renders friendly labels for raw and IBM-qualified identifiers", () => {
    expect(friendlyToolName("verify_synthetic_identity")).toBe("Verify Identity");
    expect(friendlyToolName("veteran-access-mcp-remote-m64-canary:search_availability")).toBe(
      "Find Appointments",
    );
    expect(friendlyToolActivity("search_availability")).toBe("Searching available appointments");
  });

  it("does not display unknown tool identifiers to callers", () => {
    expect(friendlyToolName("unknown_internal_tool")).toBe("Other Tool Activity");
  });
});
