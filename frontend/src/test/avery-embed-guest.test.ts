import { describe, expect, it } from "vitest";
import {
  embedGuestConfig,
  newGuestCookie,
  readGuestCookie,
  reserveGuestEmbedToken,
} from "@/lib/avery-embed-guest";

const origin = "https://vab-avery-callcenter.example.test";
const env = {
  VAB_PUBLIC_AVERY_EMBED_ENABLED: "true",
  VAB_PUBLIC_AVERY_EMBED_ORIGIN: origin,
  VAB_API_BASE_URL: "https://vab-canary.example.test",
  VAB_EMBED_TOKEN_SERVICE_KEY: "s".repeat(48),
  VAB_EMBED_GUEST_COOKIE_KEY: "c".repeat(48),
};

function request(headers: Record<string, string> = {}) {
  return new Request(`${origin}/api/avery-embed-token`, {
    method: "POST",
    headers: {
      host: new URL(origin).host,
      origin,
      "sec-fetch-site": "same-origin",
      "x-vab-guest-embed": "1",
      "content-type": "application/json",
      ...headers,
    },
    body: "{}",
  });
}

describe("secure IBM Avery guest embed token gateway", () => {
  it("fails closed unless separately enabled for exact HTTPS origin", () => {
    expect(embedGuestConfig(env, request())).not.toBeNull();
    expect(
      embedGuestConfig({ ...env, VAB_PUBLIC_AVERY_EMBED_ENABLED: "false" }, request()),
    ).toBeNull();
    expect(
      embedGuestConfig({ ...env, VAB_PUBLIC_AVERY_EMBED_ORIGIN: "http://test" }, request()),
    ).toBeNull();
    expect(embedGuestConfig({ ...env, VAB_EMBED_TOKEN_SERVICE_KEY: "" }, request())).toBeNull();
    expect(
      embedGuestConfig(
        { ...env, VAB_EMBED_GUEST_COOKIE_KEY: env.VAB_EMBED_TOKEN_SERVICE_KEY },
        request(),
      ),
    ).toBeNull();
    expect(
      embedGuestConfig({ ...env, VAB_API_BASE_URL: "http://vab.example.test" }, request()),
    ).toBeNull();
  });

  it("rejects arbitrary clients and cross-origin browser requests", () => {
    expect(embedGuestConfig(env, request({ origin: "https://bad.example" }))).toBeNull();
    expect(embedGuestConfig(env, request({ host: "bad.example" }))).toBeNull();
    expect(embedGuestConfig(env, request({ "sec-fetch-site": "cross-site" }))).toBeNull();
    expect(embedGuestConfig(env, request({ "x-vab-guest-embed": "0" }))).toBeNull();
    expect(embedGuestConfig(env, request({ authorization: "Bearer x" }))).toBeNull();
    expect(embedGuestConfig(env, request({ "content-type": "text/plain" }))).toBeNull();
  });

  it("binds a rotating JWT to one signed HttpOnly, short-lived browser session", async () => {
    const key = env.VAB_EMBED_GUEST_COOKIE_KEY;
    const now = 1_800_000_000_000;
    const guest = await newGuestCookie(key, now);
    expect(guest.id).toMatch(/^[a-f0-9]{32}$/);
    expect(guest.header).toContain("HttpOnly; Secure; SameSite=Strict");
    expect(await readGuestCookie(`vab_avery_guest=${guest.value}`, key, now + 1000)).toBe(guest.id);
    expect(await readGuestCookie(`vab_avery_guest=${guest.value}`, "x".repeat(48), now)).toBeNull();
    expect(
      await readGuestCookie(`vab_avery_guest=${guest.value}`, key, now + 3_601_000),
    ).toBeNull();
    const tampered = `${guest.value[0] === "f" ? "e" : "f"}${guest.value.slice(1)}`;
    expect(await readGuestCookie(`vab_avery_guest=${tampered}`, key, now)).toBeNull();
  });

  it("bounds repeated token issuance per guest", () => {
    const id = "c".repeat(32);
    const now = 1_900_000_000_000;
    for (let i = 0; i < 8; i++) expect(reserveGuestEmbedToken(id, i === 0, now)).toBe(true);
    expect(reserveGuestEmbedToken(id, false, now)).toBe(false);
  });
});
