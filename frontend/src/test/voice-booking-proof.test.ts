import { describe, expect, it } from "vitest";
import { readVoiceBookingProof } from "../lib/voice-booking-proof";

const receipt = {
  verified: true,
  identity_verified: true,
  state: "BOOKED_SIMULATED",
  booking_case_id: "VAB-DEMO-20261113-CASE-032",
  voice_session_id: "vs-current",
  begins_at: "2026-11-24T16:00:00Z",
  ends_at: "2026-11-24T16:30:00Z",
  appointment_id: "a312dfdf-3859-5a5b-a3b9-c8bf25141e7f",
  token: "private",
};

describe("trusted voice booking receipt", () => {
  it("preserves receipt clinic and rejects malformed names", () => {
    const parse = (extra: object) =>
      readVoiceBookingProof(
        { ...receipt, ...extra },
        "simulated_booking_recorded",
        "application",
        "vs-current",
      );
    expect(parse({ clinic_name: "Verified test clinic" })?.clinic_name).toBe(
      "Verified test clinic",
    );
    expect(parse({ clinic_name: "Verified test clinic" })).not.toHaveProperty("provider_name");
    expect(parse({ clinic_name: "Other\nclinic" })).toBeNull();
    expect(parse({ provider_name: { name: "Invented" } })).toBeNull();
  });
  it("accepts a dynamic case only with verified current-call host evidence", () => {
    const dynamic = {
      ...receipt,
      booking_case_id: "VAB-CALL-a312dfdf-3859-5a5b-a3b9-c8bf25141e7f",
    };
    expect(
      readVoiceBookingProof(dynamic, "simulated_booking_recorded", "application", "vs-current"),
    ).not.toBeNull();
    expect(
      readVoiceBookingProof(dynamic, "simulated_booking_recorded", "application", "vs-other"),
    ).toBeNull();
    expect(
      readVoiceBookingProof(
        dynamic,
        "simulated_booking_recorded",
        "watsonx_orchestrate",
        "vs-current",
      ),
    ).toBeNull();
    expect(
      readVoiceBookingProof(
        { ...dynamic, booking_case_id: "VAB-CALL-arbitrary" },
        "simulated_booking_recorded",
        "application",
        "vs-current",
      ),
    ).toBeNull();
  });
  it("retains only safe proof fields for this call", () => {
    const proof = readVoiceBookingProof(
      receipt,
      "simulated_booking_recorded",
      "application",
      "vs-current",
    );
    expect(proof?.appointment_id).toBe(receipt.appointment_id);
    expect(proof).not.toHaveProperty("token");
  });
  it("rejects another call or model-authored evidence", () => {
    expect(
      readVoiceBookingProof(receipt, "simulated_booking_recorded", "application", "vs-other"),
    ).toBeNull();
    expect(
      readVoiceBookingProof(
        receipt,
        "simulated_booking_recorded",
        "watsonx_orchestrate",
        "vs-current",
      ),
    ).toBeNull();
  });
  it.each([
    { verified: "true" },
    { identity_verified: false },
    { state: "BOOKED" },
    { appointment_id: "invented" },
    { begins_at: "2026-11-24T16:00:00" },
    { ends_at: "2026-11-24T15:00:00Z" },
    { booking_case_id: "another-case" },
  ])("rejects malformed proof %j", (change) => {
    expect(
      readVoiceBookingProof(
        { ...receipt, ...change },
        "simulated_booking_recorded",
        "application",
        "vs-current",
      ),
    ).toBeNull();
  });
  it("does not turn an offer into a booking", () => {
    const proof = readVoiceBookingProof(
      { ...receipt, state: "OFFERED" },
      "slot_verified",
      "application",
      "vs-current",
    );
    expect(proof?.state).toBe("OFFERED");
    expect(proof).not.toHaveProperty("appointment_id");
  });
});

it("projects automatic CRM notes only with verified host booking provenance", () => {
  const parse = (extra: object) =>
    readVoiceBookingProof(
      { ...receipt, ...extra },
      "simulated_booking_recorded",
      "application",
      "vs-current",
    );
  const saved = {
    crm_note_status: "SAVED",
    crm_note_id: receipt.appointment_id,
    crm_note_origin: "trusted_booking_host",
    crm_note_text: "private",
  };
  expect(parse(saved)?.crm_note_status).toBe("SAVED");
  expect(parse(saved)).not.toHaveProperty("crm_note_text");
  expect(parse({ ...saved, crm_note_origin: "agent" })).not.toHaveProperty("crm_note_status");
  expect(parse({ ...saved, crm_note_id: "invented" })).not.toHaveProperty("crm_note_status");
  const pending = parse({ ...saved, crm_note_status: "PENDING" });
  expect(pending?.crm_note_status).toBe("PENDING");
  expect(pending).not.toHaveProperty("crm_note_id");
});
