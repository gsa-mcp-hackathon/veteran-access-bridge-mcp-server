import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { readVoiceAppointmentOptions } from "@/lib/voice-appointment-options";
import { ChatAppointmentOptions } from "@/components/msa/chat-appointment-options";

const payload = {
  verified: true,
  identity_verified: true,
  booking_case_id: "VAB-DEMO-20261113-CASE-046",
  voice_session_id: "vs-current",
  patient_time_zone: "America/Los_Angeles",
  options: [
    {
      option_id: "option-1",
      begins_at: "2026-11-25T16:00:00Z",
      ends_at: "2026-11-25T16:30:00Z",
      provider_name: null,
      clinic_name: "Demo Primary Care",
      service: "PRIMARY_CARE",
      private_token: "secret",
    },
  ],
};
const parse = (p: unknown = payload, source = "application", voice = "vs-current") =>
  readVoiceAppointmentOptions(p, "options_presented", source, voice);
afterEach(cleanup);
describe("call-bound appointment cards", () => {
  it("renders dynamic case options without accepting another call's inventory", () => {
    const dynamic = {
      ...payload,
      booking_case_id: "VAB-CALL-a312dfdf-3859-5a5b-a3b9-c8bf25141e7f",
    };
    render(<ChatAppointmentOptions data={parse(dynamic)!} current />);
    expect(screen.getByText("Demo Primary Care")).toBeInTheDocument();
    expect(parse(dynamic, "application", "vs-other")).toBeNull();
  });
  it("displays patient-local dates and missing provider information honestly", () => {
    const proof = parse()!;
    expect(proof.options[0]).not.toHaveProperty("private_token");
    render(<ChatAppointmentOptions data={proof} current />);
    expect(screen.getByText(/8:00 AM PST/)).toBeInTheDocument();
    expect(screen.getByText("Wednesday")).toBeInTheDocument();
    expect(screen.getByText(/Provider not supplied/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("rejects model-authored and cross-call inventory", () => {
    expect(parse(payload, "watsonx_orchestrate")).toBeNull();
    expect(parse(payload, "application", "vs-other")).toBeNull();
  });
  it.each([
    { identity_verified: false },
    { patient_time_zone: "UTC" },
    { options: [...payload.options, ...payload.options] },
    { options: [{ ...payload.options[0], begins_at: "2026-11-25T16:00:00" }] },
    { options: [{ ...payload.options[0], service: "CARDIOLOGY" }] },
  ])("rejects invalid evidence %j", (change) =>
    expect(parse({ ...payload, ...change })).toBeNull(),
  );
});
