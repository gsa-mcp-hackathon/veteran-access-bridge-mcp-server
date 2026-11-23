import { describe, expect, it } from "vitest";
import { readCrmProof, crmProofPayload } from "../lib/crm-proof";

const payload = {
  tool_name: "record_crm_interaction",
  tool_call_id: "tool-1",
  status: "succeeded",
  evidence: "server_scope_receipt",
  scope_verified: true,
  invoked_by: "agent",
  verified_case_id: "case-A",
  voice_session_id: "voice-A",
  crm_receipt: {
    persisted: true,
    synthetic: true,
    booking_created: false,
    operation: "record_crm_interaction",
    record_id: "b556f32a-d290-449e-afcd-65a0ba429fdf",
    version: 1,
    case_id: "case-A",
    interaction_id: "call-A",
    actor: "AVERY",
    replayed: false,
    summary: "never forward notes",
  },
};
const read = (p: unknown, source = "application", interaction = "call-A", voice = "voice-A") =>
  readCrmProof(p, "mcp_tool_result", source, interaction, voice);
describe("CRM evidence", () => {
  it("strips content and preserves validated metadata through the gateway", () => {
    const proof = read(payload)!;
    expect(proof.record_id).toBe(payload.crm_receipt.record_id);
    const safe = { ...payload, ...crmProofPayload(proof) };
    expect(JSON.stringify(safe)).not.toContain("never forward");
    expect(read(safe)).toEqual(proof);
  });
  it("rejects other sessions and model claims", () => {
    expect(read(payload, "watsonx_orchestrate")).toBeNull();
    expect(read(payload, "application", "call-B")).toBeNull();
    expect(read(payload, "application", "call-A", "voice-B")).toBeNull();
  });
  it.each([
    { persisted: false },
    { booking_created: true },
    { synthetic: false },
    { case_id: "case-B" },
    { version: 0 },
    { record_id: "invalid" },
    { operation: "get_crm_case" },
  ])("rejects malformed or mismatched receipt %s", (change) => {
    expect(read({ ...payload, crm_receipt: { ...payload.crm_receipt, ...change } })).toBeNull();
  });
});
