import { afterEach, describe, expect, it, vi } from "vitest";
import { Route as CallRoute } from "@/routes/api/demo-call";
import { Route as MonitorRoute } from "@/routes/api/msa-monitor";
import { MAX_GATEWAY_BODY_BYTES } from "@/lib/bounded-json";

type HandlerOptions = {
  server: { handlers: { POST: (input: { request: Request }) => Promise<Response> } };
};
const origin = "https://caller.example.test";
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("gateway body limits precede backend operations", () => {
  it.each([
    ["/api/demo-call", CallRoute],
    ["/api/msa-monitor", MonitorRoute],
  ] as const)("rejects oversized input to %s without calling the backend", async (path, route) => {
    vi.stubEnv("VAB_MSA_LIVE_MONITOR_ENABLED", "true");
    vi.stubEnv("VAB_API_BASE_URL", "https://backend.example.test");
    vi.stubEnv("VAB_MSA_MONITOR_SERVICE_KEY", "k".repeat(32));
    vi.stubEnv("VAB_MSA_OPERATOR_ACCESS_CODE", "c".repeat(32));
    vi.stubEnv("VAB_PUBLIC_GUEST_CALL_ENABLED", "true");
    vi.stubEnv("VAB_PUBLIC_GUEST_ORIGIN", origin);
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (path === "/api/demo-call")
      Object.assign(headers, {
        host: "caller.example.test",
        origin,
        "sec-fetch-site": "same-origin",
        "x-vab-guest-call": "1",
      });
    else headers["authorization"] = `Bearer ${"c".repeat(32)}`;
    const request = new Request(origin + path, {
      method: "POST",
      headers,
      body: JSON.stringify({ action: "start", extra: "x".repeat(MAX_GATEWAY_BODY_BYTES) }),
    });
    const response = await (route.options as unknown as HandlerOptions).server.handlers.POST({
      request,
    });
    expect(response.status).toBe(413);
    expect(await response.json()).toEqual({ error: "invalid_request" });
    expect(fetch).not.toHaveBeenCalled();
  });
});
