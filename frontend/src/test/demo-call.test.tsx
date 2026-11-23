import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DemoCaller } from "@/components/msa/demo-caller";
import { INTAKE_CASE_ID, parseDemoCallAction } from "@/lib/demo-call-gateway";
import { Route as DemoCallRoute } from "@/routes/demo-call";
import { Route as DemoCallApiRoute } from "@/routes/api/demo-call";

afterEach(cleanup);

describe("incoming synthetic call", () => {
  it("never preselects a patient or renders the synthetic roster", () => {
    render(<DemoCaller />);
    expect(
      screen.getByRole("heading", { name: "Autonomous Scheduling Command Center" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Initiate Demo Call/i })).toBeDisabled();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByText("Mariano761 Ruelas156")).toBeNull();
    expect(screen.getByText(/No patient is preselected or revealed here/)).toBeInTheDocument();
  });

  it("accepts start with no patient ID and strips caller-supplied selectors", () => {
    expect(INTAKE_CASE_ID).toBe("DEMO-PC-VOICE-INTAKE-001");
    expect(parseDemoCallAction({ action: "start" })).toEqual({ action: "start" });
    expect(parseDemoCallAction({ action: "start", case_id: "DEMO-PC-P217-001" })).toEqual({
      action: "start",
    });
    expect(parseDemoCallAction({ action: "list" })).toBeNull();
    expect(parseDemoCallAction({ action: "connected", voice_session_id: "../bad" })).toBeNull();
  });

  it("registers the real caller and gateway routes in the separate frontend", () => {
    expect(DemoCallRoute).toBeDefined();
    expect(DemoCallApiRoute).toBeDefined();
  });
});
