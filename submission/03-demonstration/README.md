# 03 · Demonstration

[**Watch the recorded Avery video directly**](../../docs/assets/avery-demo.mp4) · [Read the walkthrough](../../docs/demonstration.md).

**Final demonstration call (3:39, same call as presentation slides 10–11).** A trusted voice service verified the synthetic caller. IBM then selected four MCP tools: `get_va_patient_health_sandbox_summary`, `search_call_appointments`, `select_call_appointment` and `book_call_appointment`. Trusted backend services checked identity, current consent, slot and policy before committing the booking, then confirmed it by independent database readback: Primary Care, Friday, December 4, 2026, 9:00 AM CST, synthetic confirmation `51976dfb-30da-5f04-a628-e9ca1ec31fd9`. After hang-up, the trusted booking service saved a CRM note and generated a confirmation letter (not sent).

Key moments: about **2:00** patient-health read · **3:12** booking confirmed · **3:36** wrap-up complete.

An earlier accepted trial (November 16, CASE-047, backend revision 00037) recorded five IBM-selected tool types, one synthetic appointment and one host-written CRM note; it is documented separately and does not validate a later release.

[Recorded evidence and boundaries](../../docs/evaluation/validation-agent.md#end-to-end-voice-trial).
