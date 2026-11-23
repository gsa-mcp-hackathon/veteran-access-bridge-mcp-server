import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SchedulingEncounterSummary } from "@/components/msa/unified-workspace-panels";
import type { VoiceAppointmentOptions } from "@/lib/voice-appointment-options";

afterEach(cleanup);
const options: VoiceAppointmentOptions = {
  verified: true,
  identity_verified: true,
  booking_case_id: "VAB-DEMO-20261113-CASE-046",
  voice_session_id: "vs-current",
  patient_time_zone: "America/Chicago",
  options: [
    {
      option_id: "test-1",
      begins_at: "2026-11-25T16:00:00Z",
      ends_at: "2026-11-25T16:30:00Z",
      service: "PRIMARY_CARE",
      clinic_name: "Verified test clinic",
      provider_name: null,
    },
  ],
};
it("shows the common clinic from verified appointment options", () => {
  render(
    <SchedulingEncounterSummary
      identityVerified
      caseId={options.booking_case_id}
      appointmentOptions={options}
    />,
  );
  expect(screen.getByText("Verified test clinic")).toBeInTheDocument();
});
it("does not pick one clinic from inconsistent offers", () => {
  render(
    <SchedulingEncounterSummary
      identityVerified
      caseId={options.booking_case_id}
      appointmentOptions={{
        ...options,
        options: [
          ...options.options,
          { ...options.options[0]!, option_id: "test-2", clinic_name: "Another clinic" },
        ],
      }}
    />,
  );
  expect(screen.getByText("Not resolved")).toBeInTheDocument();
});

it("shows the explicitly mapped facility instead of the demo inventory label", () => {
  render(
    <SchedulingEncounterSummary
      identityVerified
      caseId={options.booking_case_id}
      appointmentOptions={{
        ...options,
        options: [{ ...options.options[0]!, facility_name: "Verified VA facility" }],
      }}
    />,
  );
  expect(screen.getByText("Verified VA facility")).toBeInTheDocument();
  expect(screen.queryByText("Verified test clinic")).not.toBeInTheDocument();
});
