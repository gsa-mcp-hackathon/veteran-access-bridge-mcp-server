import { describe, expect, it, vi } from "vitest";
import {
  guestActivityScope,
  guestCallConfig,
  registerGuestSession,
  guestSessionDeadline,
  verifyGuestSession,
} from "@/lib/public-guest-gate";
import { authorizeSandboxRequest } from "@/lib/one-click-gate";

const origin = "https://vab-avery-callcenter.example.test";
const env = {
  VAB_PUBLIC_GUEST_CALL_ENABLED: "true",
  VAB_PUBLIC_GUEST_ORIGIN: origin,
  VAB_MSA_LIVE_MONITOR_ENABLED: "true",
  VAB_MSA_MONITOR_SERVICE_KEY: "k".repeat(32),
  VAB_MSA_OPERATOR_ACCESS_CODE: "c".repeat(32),
  VAB_API_BASE_URL: "https://vab-canary.example.test",
  VAB_MSA_ONE_CLICK_DEMO_ENABLED: "false",
};

function request(headers: Record<string, string> = {}, path = "/api/demo-call") {
  return new Request(`${origin}${path}`, {
    method: "POST",
    headers: {
      host: new URL(origin).host,
      origin,
      "sec-fetch-site": "same-origin",
      "x-vab-guest-call": "1",
      "content-type": "application/json",
      ...headers,
    },
  });
}

describe("temporary public synthetic guest calls", () => {
  it("allows only same-call teardown retries during expiry grace", () => {
    vi.useFakeTimers();
    try {
      const token = registerGuestSession("voice-expiry", {
        interactionId: "interaction_expiry",
        caseId: "DEMO-PC-VOICE-INTAKE-001",
        correlationId: "corr_expiry",
      });
      const req = request({ "x-vab-guest-session": token });
      expect(guestSessionDeadline(token)).toBe(Date.now() + 300_000);
      vi.advanceTimersByTime(300_000);
      expect(verifyGuestSession(req, "voice-expiry")).toBe(false);
      expect(guestActivityScope(req, "voice-expiry")).toBeNull();
      expect(verifyGuestSession(req, "another-call", true)).toBe(false);
      expect(verifyGuestSession(req, "voice-expiry", true)).toBe(true);
      expect(verifyGuestSession(req, "voice-expiry", true)).toBe(true);
      expect(verifyGuestSession(req, "voice-expiry")).toBe(false);
      const old = registerGuestSession("voice-grace-ended");
      vi.advanceTimersByTime(360_000);
      expect(
        verifyGuestSession(request({ "x-vab-guest-session": old }), "voice-grace-ended", true),
      ).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
  it("requires an explicit feature flag and fixed HTTPS origin", () => {
    expect(guestCallConfig(env, request())).not.toBeNull();
    expect(
      guestCallConfig({ ...env, VAB_PUBLIC_GUEST_CALL_ENABLED: "false" }, request()),
    ).toBeNull();
    expect(
      guestCallConfig({ ...env, VAB_PUBLIC_GUEST_ORIGIN: "http://bad" }, request()),
    ).toBeNull();
    expect(guestCallConfig({ ...env, VAB_MSA_MONITOR_SERVICE_KEY: "" }, request())).toBeNull();
    expect(
      guestCallConfig({ ...env, VAB_MSA_LIVE_MONITOR_ENABLED: "false" }, request()),
    ).toBeNull();
  });
  it("rejects cross-site, forged host, missing origin, missing custom header and bearer auth", () => {
    expect(guestCallConfig(env, request({ origin: "https://evil.example" }))).toBeNull();
    expect(guestCallConfig(env, request({ host: "evil.example" }))).toBeNull();
    expect(guestCallConfig(env, request({ "sec-fetch-site": "cross-site" }))).toBeNull();
    expect(guestCallConfig(env, request({ "x-vab-guest-call": "0" }))).toBeNull();
    expect(guestCallConfig(env, request({ authorization: "Bearer wrong" }))).toBeNull();
  });
  it("does not authorize the separate operator monitor route", async () => {
    const auth = await authorizeSandboxRequest(env, request({}, "/api/msa-monitor"));
    expect(auth.ok).toBe(false);
  });
  it("binds operational activity to server-recorded call/interaction/correlation only", () => {
    const token = registerGuestSession("voice-activity", {
      interactionId: "interaction_123",
      caseId: "DEMO-PC-VOICE-INTAKE-001",
      correlationId: "corr_123",
    });
    const req = request({ "x-vab-guest-session": token });
    expect(guestActivityScope(req, "voice-activity")).toEqual({
      interactionId: "interaction_123",
      caseId: "DEMO-PC-VOICE-INTAKE-001",
      correlationId: "corr_123",
    });
    expect(guestActivityScope(req, "some-other-session")).toBeNull();
    expect(guestActivityScope(request(), "voice-activity")).toBeNull();
    expect(
      guestActivityScope(request({ "x-vab-guest-session": "0".repeat(64) }), "voice-activity"),
    ).toBeNull();
    expect(
      guestActivityScope(request({ "x-vab-guest-session": token }), "voice-activity"),
    ).not.toHaveProperty("serviceKey");
    expect(verifyGuestSession(req, "voice-activity", true)).toBe(true);
    expect(guestActivityScope(req, "voice-activity")).toBeNull();
  });

  it("binds lifecycle updates to the newly created guest call only", () => {
    const token = registerGuestSession("voice-demo-1");
    expect(token).toMatch(/^[0-9a-f]{64}$/);
    expect(verifyGuestSession(request({ "x-vab-guest-session": token }), "voice-demo-2")).toBe(
      false,
    );
    expect(verifyGuestSession(request({ "x-vab-guest-session": token }), "voice-demo-1")).toBe(
      true,
    );
    expect(
      verifyGuestSession(request({ "x-vab-guest-session": token }), "voice-demo-1", true),
    ).toBe(true);
    expect(verifyGuestSession(request({ "x-vab-guest-session": token }), "voice-demo-1")).toBe(
      false,
    );
  });
});
