import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { LiveConversationFeed } from "@/components/msa/unified-workspace-panels";
import { AfterCallWork } from "@/components/msa/screen-a-after-call";
import type { MonitorEvent } from "@/lib/live-monitor";
import { projectAfterCall } from "@/lib/after-call";

afterEach(cleanup);
const common = {
  source: "application",
  occurred_at: "2026-11-17T01:00:00Z",
  correlation_id: "corr",
};
const offers: MonitorEvent = {
  ...common,
  event_id: "offers",
  event_type: "options_presented",
  appointment_options: {
    verified: true,
    identity_verified: true,
    booking_case_id: "VAB-DEMO-20261113-CASE-046",
    voice_session_id: "vs-test",
    patient_time_zone: "America/Chicago",
    options: [
      {
        option_id: "one",
        begins_at: "2026-11-25T15:00:00Z",
        ends_at: "2026-11-25T15:30:00Z",
        provider_name: null,
        clinic_name: "Same Clinic",
        service: "PRIMARY_CARE",
      },
    ],
  },
};
const booked: MonitorEvent = {
  ...common,
  event_id: "booked",
  event_type: "simulated_booking_recorded",
  voice_booking: {
    verified: true,
    identity_verified: true,
    state: "BOOKED_SIMULATED",
    booking_case_id: "VAB-DEMO-20261113-CASE-046",
    voice_session_id: "vs-test",
    begins_at: "2026-11-25T15:00:00Z",
    ends_at: "2026-11-25T15:30:00Z",
    patient_time_zone: "America/Chicago",
    appointment_id: "verified-receipt",
  },
};
const props = {
  transcript: [],
  steps: [],
  callActive: true,
  observerError: "",
  observerPhase: "connected",
};

it("replaces offered cards with one confirmed card while retaining audit history", () => {
  const { rerender } = render(<LiveConversationFeed {...props} events={[offers]} />);
  expect(screen.getByText("Same Clinic")).toBeInTheDocument();
  rerender(<LiveConversationFeed {...props} events={[offers, booked]} />);
  expect(screen.queryByText("Same Clinic")).not.toBeInTheDocument();
  expect(screen.getAllByRole("article", { name: "Confirmed appointment" })).toHaveLength(1);
  expect(screen.getByText(/9:00:00 AM CST/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "MCP & Telemetry" }));
  expect(screen.getByText("Same Clinic")).toBeInTheDocument();
});

it("shows only the selected slot until the booking receipt arrives", () => {
  const selected: MonitorEvent = {
    ...booked,
    event_id: "selection",
    event_type: "slot_verified",
    voice_booking: { ...booked.voice_booking!, state: "OFFERED" },
  };
  delete selected.voice_booking!.appointment_id;
  const { rerender } = render(<LiveConversationFeed {...props} events={[offers, selected]} />);
  expect(screen.getByRole("article", { name: "Selected appointment" })).toBeInTheDocument();
  expect(screen.queryByText("Your appointment options")).toBeNull();
  expect(screen.queryByText("Appointment saved and verified")).toBeNull();
  rerender(<LiveConversationFeed {...props} events={[offers, selected, booked]} />);
  expect(screen.queryByRole("article", { name: "Selected appointment" })).toBeNull();
  expect(screen.getByRole("article", { name: "Confirmed appointment" })).toBeInTheDocument();
});

it("pauses following when the user scrolls up and provides a jump back", () => {
  render(<LiveConversationFeed {...props} events={[]} />);
  const panel = screen.getByRole("tabpanel");
  Object.defineProperties(panel, {
    scrollHeight: { value: 1000 },
    clientHeight: { value: 200 },
    scrollTop: { value: 100, writable: true },
  });
  fireEvent.scroll(panel);
  fireEvent.click(screen.getByRole("button", { name: "Jump to latest" }));
  expect(panel.scrollTop).toBe(1000);
  expect(screen.queryByRole("button", { name: "Jump to latest" })).not.toBeInTheDocument();
});

it("places the saved letter in Wrap Up without the contradictory unavailable placeholder", () => {
  const saved = projectAfterCall({
    status: "COMPLETE",
    persisted: true,
    summary: "Call complete.",
    record_id: "11111111-1111-4111-8111-111111111111",
    letter: { text: "Confirmed appointment.", delivery_status: "NOT_SENT" },
  });
  render(<AfterCallWork ended receipt={null} afterCall={saved} />);
  expect(screen.getByRole("link", { name: "Download appointment letter" })).toBeInTheDocument();
  expect(screen.queryByText(/Unavailable without persisted/)).not.toBeInTheDocument();
});
