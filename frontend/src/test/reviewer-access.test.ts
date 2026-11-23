import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { ReviewerEnv } from "@/lib/reviewer-access";

const origin = "https://review.example.test";
const env: ReviewerEnv = {
  VAB_REVIEWER_LOGIN_ENABLED: "true",
  VAB_REVIEWER_ACCESS_CODE: "r".repeat(32),
  VAB_PUBLIC_GUEST_ORIGIN: origin,
};
let gate: typeof import("@/lib/reviewer-access").reviewerAccess;
const req = (path: string, token?: string) =>
  new Request(origin + path, { headers: token ? { cookie: token } : {} });
const login = (code = env.VAB_REVIEWER_ACCESS_CODE, from = origin) =>
  new Request(origin + "/api/reviewer-login", {
    method: "POST",
    headers: { origin: from, "content-type": "application/json" },
    body: JSON.stringify({ code }),
  });
beforeEach(async () => {
  vi.resetModules();
  gate = (await import("@/lib/reviewer-access")).reviewerAccess;
});
afterEach(() => vi.useRealTimers());

describe("server-enforced reviewer access", () => {
  it("protects pages, API and old operator routes without a cookie", async () => {
    expect((await gate(req("/"), env))?.status).toBe(303);
    expect((await gate(req("/demo-call"), env))?.headers.get("location")).toBe("/login");
    for (const path of ["/api/demo-call", "/api/msa-monitor", "/api/avery-embed-token"]) {
      expect((await gate(req(path), env))?.status).toBe(401);
    }
    const page = await gate(req("/login"), env);
    expect(await page?.text()).toContain("Reviewer sign in");
    expect(page?.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
  });
  it("fails closed for missing or reused privileged secrets", async () => {
    expect((await gate(req("/"), { ...env, VAB_REVIEWER_ACCESS_CODE: "" }))?.status).toBe(503);
    expect(
      (await gate(req("/"), { ...env, VAB_MSA_OPERATOR_ACCESS_CODE: "r".repeat(32) }))?.status,
    ).toBe(503);
    expect(await gate(req("/"), { ...env, VAB_REVIEWER_LOGIN_ENABLED: "false" })).toBeNull();
  });
  it("rejects wrong credentials, cross-origin requests and oversized login bodies", async () => {
    expect((await gate(login("incorrect"), env))?.status).toBe(401);
    expect(
      (await gate(login(env.VAB_REVIEWER_ACCESS_CODE, "https://evil.example"), env))?.status,
    ).toBe(403);
    expect((await gate(login("x".repeat(17000)), env))?.status).toBe(413);
  });
  it("issues opaque secure cookies and rejects tampering, expiry and rotation", async () => {
    vi.useFakeTimers();
    const response = await gate(login(), env);
    expect(response?.status).toBe(200);
    const setCookie = response?.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain("Secure; HttpOnly; SameSite=Strict");
    expect(setCookie).not.toContain(env.VAB_REVIEWER_ACCESS_CODE);
    const token = setCookie.split(";")[0];
    expect(await gate(req("/", token), env)).toBeNull();
    expect(
      (await gate(req("/api/demo-call", "__Host-vab-reviewer=" + "0".repeat(64)), env))?.status,
    ).toBe(401);
    expect(
      (
        await gate(req("/api/demo-call", token), {
          ...env,
          VAB_REVIEWER_ACCESS_CODE: "s".repeat(32),
        })
      )?.status,
    ).toBe(401);
    vi.advanceTimersByTime(3_600_000);
    expect((await gate(req("/api/demo-call", token), env))?.status).toBe(401);
  });
  it("revokes the session on same-origin logout and rejects replay", async () => {
    const token = (await gate(login(), env))?.headers.get("set-cookie")?.split(";")[0] ?? "";
    const logout = new Request(origin + "/api/reviewer-logout", {
      method: "POST",
      headers: { origin, cookie: token },
    });
    expect((await gate(logout, env))?.status).toBe(200);
    expect((await gate(req("/api/demo-call", token), env))?.status).toBe(401);
  });
  it("bounds guessing attempts without trusting a client-supplied IP", async () => {
    for (let i = 0; i < 10; i++) expect((await gate(login("wrong"), env))?.status).toBe(401);
    expect((await gate(login(), env))?.status).toBe(429);
  });
});
