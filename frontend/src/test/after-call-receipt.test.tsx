import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AfterCallWork } from "../components/msa/screen-a-after-call";
import { readVoiceBookingProof } from "../lib/voice-booking-proof";
import { projectAfterCall } from "../lib/after-call";

afterEach(cleanup);
const raw = {
  verified: true,
  identity_verified: true,
  state: "BOOKED_SIMULATED",
  booking_case_id: "VAB-DEMO-20261113-CASE-037",
  voice_session_id: "vs-test",
  begins_at: "2026-11-25T15:00:00Z",
  ends_at: "2026-11-25T15:30:00Z",
  appointment_id: "1e4fdb8a-eaea-572b-9459-1f6d15994242",
};

const completedAfterCall = projectAfterCall({
  status: "COMPLETE",
  persisted: true,
  summary: "Verified appointment recorded; after-call note saved.",
  record_id: "11111111-1111-4111-8111-111111111111",
  letter: { text: "Verified appointment confirmation.", delivery_status: "NOT_SENT" },
});

it.each([
  { ended: false, note: "SAVED", letter: true, expected: "pending" },
  { ended: true, note: "PENDING", letter: true, expected: "pending" },
  { ended: true, note: "SAVED", letter: false, expected: "pending" },
  { ended: true, note: "SAVED", letter: true, expected: "complete" },
])("only turns green for verified completed wrap-up: %j", ({ ended, note, letter, expected }) => {
  const proof = readVoiceBookingProof(
    {
      ...raw,
      crm_note_status: note,
      crm_note_id: raw.appointment_id,
      crm_note_origin: "trusted_booking_host",
    },
    "simulated_booking_recorded",
    "application",
    "vs-test",
  );
  render(
    <AfterCallWork
      ended={ended}
      receipt={null}
      bookingProof={proof}
      afterCall={
        completedAfterCall && {
          ...completedAfterCall,
          letter: letter ? (completedAfterCall.letter ?? null) : null,
        }
      }
    />,
  );
  const panel = screen.getByRole("region", { name: "Wrap Up" });
  expect(panel).toHaveAttribute("data-completion-state", expected);
  expect(panel.classList.contains("bg-emerald-50")).toBe(expected === "complete");
  expect(screen.getByRole("status")).toHaveTextContent(
    expected === "complete" ? "Complete" : "Pending",
  );
  expect(screen.queryByText(/^Delivered$/)).not.toBeInTheDocument();
});

it("does not turn green merely because a call ended or a pending record claims persistence", () => {
  render(
    <AfterCallWork
      ended
      receipt={null}
      afterCall={projectAfterCall({ status: "PENDING", persisted: true })}
    />,
  );
  expect(screen.getByRole("region", { name: "Wrap Up" })).toHaveAttribute(
    "data-completion-state",
    "pending",
  );
});

describe("after-call verified receipt", () => {
  it("shows a validated call-bound receipt without inventing a letter", () => {
    const proof = readVoiceBookingProof(
      raw,
      "simulated_booking_recorded",
      "application",
      "vs-test",
    );
    render(<AfterCallWork ended receipt={null} bookingProof={proof} />);
    expect(
      screen.getByRole("article", { name: "Verified synthetic booking receipt" }),
    ).toHaveTextContent(raw.appointment_id);
    expect(screen.getByRole("button", { name: "Preview Letter" })).toBeDisabled();
  });
  it.each(["vs-other", undefined])(
    "does not display unverified or mismatched evidence (%s)",
    (voice) => {
      const proof = voice
        ? readVoiceBookingProof(raw, "simulated_booking_recorded", "application", voice)
        : null;
      render(<AfterCallWork ended receipt={null} bookingProof={proof} />);
      expect(
        screen.queryByRole("article", { name: "Verified synthetic booking receipt" }),
      ).toBeNull();
    },
  );
  it("does not present an offer as a booking", () => {
    const proof = readVoiceBookingProof(
      { ...raw, state: "OFFERED" },
      "slot_verified",
      "application",
      "vs-test",
    );
    render(<AfterCallWork ended receipt={null} bookingProof={proof} />);
    expect(
      screen.queryByRole("article", { name: "Verified synthetic booking receipt" }),
    ).toBeNull();
  });
});

it.each(["SAVED", "PENDING"])(
  "shows automatic CRM note %s separately from agent actions",
  (status) => {
    const proof = readVoiceBookingProof(
      {
        ...raw,
        crm_note_status: status,
        crm_note_id: raw.appointment_id,
        crm_note_origin: "trusted_booking_host",
      },
      "simulated_booking_recorded",
      "application",
      "vs-test",
    );
    render(<AfterCallWork ended receipt={null} bookingProof={proof} />);
    expect(screen.getByRole("article", { name: "CRM save receipts" })).toHaveTextContent(
      status === "SAVED" ? "Automatic booking note saved" : "Automatic booking note pending",
    );
    expect(
      screen.getByRole("article", { name: "Verified synthetic booking receipt" }),
    ).toHaveTextContent(raw.appointment_id);
  },
);
