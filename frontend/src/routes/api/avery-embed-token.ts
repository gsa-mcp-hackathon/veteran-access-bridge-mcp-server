import { createFileRoute } from "@tanstack/react-router";
import {
  embedGuestConfig,
  newGuestCookie,
  readGuestCookie,
  reserveGuestEmbedToken,
  type EmbedGuestEnv,
} from "@/lib/avery-embed-guest";

/**
 * Same-origin, synthetic-only guest JWT broker for IBM's secured embedded chat.
 * The browser receives its own expiring RS256 JWT, never the IBM signing key
 * or the VAB embed-issuer service secret.
 *
 * Do not enable on a public deployment until the MCP synthetic-only scope,
 * tenant embed security, edge rate limits and anonymous session policy pass review.
 */
function reply(body: unknown, status: number, cookie?: string): Response {
  const headers = new Headers({
    "Content-Type": "application/json",
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    Vary: "Cookie, Origin",
  });
  if (cookie) headers.set("Set-Cookie", cookie);
  return new Response(JSON.stringify(body), { status, headers });
}

export const Route = createFileRoute("/api/avery-embed-token")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const config = embedGuestConfig(process.env as EmbedGuestEnv, request);
        if (!config) return reply({ error: "guest_embed_disabled" }, 403);
        let raw: string;
        try {
          raw = await request.text();
        } catch {
          return reply({ error: "invalid_request" }, 400);
        }
        // This endpoint never accepts user-selected agent IDs, cases or subjects.
        if (raw.trim() !== "{}") return reply({ error: "invalid_request" }, 400);

        const oldId = await readGuestCookie(request.headers.get("cookie"), config.cookieKey);
        const fresh = oldId ? null : await newGuestCookie(config.cookieKey);
        const id = oldId ?? fresh?.id;
        if (!id) return reply({ error: "guest_embed_unavailable" }, 503);
        if (!reserveGuestEmbedToken(id, !oldId))
          return reply({ error: "guest_embed_rate_limited" }, 429);

        try {
          const upstream = await fetch(`${config.backendUrl}/api/orchestrate/guest-embed-token`, {
            method: "POST",
            redirect: "error",
            cache: "no-store",
            signal: AbortSignal.timeout(10000),
            headers: {
              Authorization: `Bearer ${config.serviceKey}`,
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            body: JSON.stringify({ guest_session_id: id }),
          });
          if (!upstream.ok) return reply({ error: "embed_issuer_unavailable" }, 502);
          const value: unknown = await upstream.json();
          if (!value || typeof value !== "object")
            return reply({ error: "embed_issuer_unavailable" }, 502);
          const payload = value as Record<string, unknown>;
          const token = payload["identityToken"];
          const expiresAt = payload["expiresAt"];
          const now = Math.floor(Date.now() / 1000);
          if (
            typeof token !== "string" ||
            !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token) ||
            token.length < 200 ||
            token.length > 5000 ||
            typeof expiresAt !== "number" ||
            !Number.isSafeInteger(expiresAt) ||
            expiresAt <= now + 30 ||
            expiresAt > now + 900
          )
            return reply({ error: "embed_issuer_unavailable" }, 502);
          return reply({ identityToken: token, expiresAt, synthetic: true }, 200, fresh?.header);
        } catch {
          return reply({ error: "embed_issuer_unavailable" }, 502);
        }
      },
    },
  },
});
