/* eslint-disable prettier/prettier -- Local sandbox work-in-progress; formatted at Codespace release gate. */
import { createFileRoute } from "@tanstack/react-router";
import { GatewayBodyError, readBoundedJson } from "@/lib/bounded-json";
import { type GatewayConfig } from "@/lib/msa-monitor-gateway";
import { projectCallerActivityPage } from "@/lib/caller-activity-projection";
import { projectAfterCall } from "@/lib/after-call";
import { INTAKE_CASE_ID, parseDemoCallAction, validateMediaToken } from "@/lib/demo-call-gateway";
import { authorizeSandboxRequest, type OneClickEnv } from "@/lib/one-click-gate";
import {
  failGuestStart,
  guestCallConfig,
  guestActivityScope,
  guestSessionDeadline,
  registerGuestSession,
  renewGuestSession,
  reserveGuestStart,
  verifyGuestSession,
  type GuestEnv,
} from "@/lib/public-guest-gate";

/**
 * Codespace-only Veteran test caller BFF. Uses the SAME backend and canonical
 * voice/interaction APIs as the old caller UI, but no secondary application
 * state machine or synthetic speech. Disabled unless both sandbox gates and
 * the separate operator code are set. No CORS, no browser service key.
 */
const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

type ValueMap = Record<string, unknown> & {
  transport?: unknown;
  browser_softphone_enabled?: unknown;
  scheduling_encounter_id?: unknown;
  case_id?: unknown;
  interaction_id?: unknown;
  correlation_id?: unknown;
  runtime_failure_code?: unknown;
  voice_session_id?: unknown;
  server_url?: unknown;
  participant_token?: unknown;
  room_name?: unknown;
};
const isMap = (v: unknown): v is ValueMap => v !== null && typeof v === "object";
const str = (v: unknown): string | null =>
  typeof v === "string" && v.length > 0 && v.length <= 256 ? v : null;

async function callBackend(
  cfg: GatewayConfig,
  path: string,
  caseId: string,
  method: "GET" | "POST" = "GET",
  body?: ValueMap,
): Promise<ValueMap> {
  const response = await fetch(cfg.baseUrl + path, {
    method,
    redirect: "error",
    signal: AbortSignal.timeout(path.endsWith("/events") ? 45000 : 15000),
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${cfg.serviceKey}`,
      "X-Demo-Role": "SCHEDULER",
      "X-Demo-Actor": "synthetic-browser-voice-launcher",
      "X-Demo-Case": caseId,
      Accept: "application/json",
      ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    // No backend error bodies, arbitrary provider strings, identity data, or
    // unbounded payloads cross into browser-facing error messages.
    throw new Error(`upstream_${response.status}`);
  }
  const data: unknown = await response.json();
  if (!isMap(data)) throw new Error("upstream_contract");
  return data;
}

export const Route = createFileRoute("/api/demo-call")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        // Only this synthetic Veteran calling endpoint accepts opted-in public
        // guests. The separate MSA monitor endpoint still demands operator auth.
        const guestConfig = guestCallConfig(process.env as GuestEnv, request);
        const guest = guestConfig !== null;
        const auth = guest
          ? null
          : await authorizeSandboxRequest(process.env as OneClickEnv, request);
        if (!guestConfig && (!auth || !auth.ok)) {
          const error = auth && !auth.ok ? auth.error : "disabled";
          return json(
            {
              error:
                error === "forbidden"
                  ? "forbidden"
                  : error === "one_click_disabled"
                    ? "demo_access_required"
                    : "demo_call_gateway_disabled",
            },
            403,
          );
        }
        const cfg = guestConfig ?? (auth && auth.ok ? auth.config : null);
        if (!cfg) return json({ error: "demo_call_gateway_disabled" }, 403);

        let input: unknown;
        try {
          input = await readBoundedJson(request);
        } catch (error) {
          return json(
            { error: "invalid_request" },
            error instanceof GatewayBodyError ? error.status : 400,
          );
        }
        const action = parseDemoCallAction(input);
        if (!action) return json({ error: "invalid_request" }, 400);

        // A guest may read only SANITIZED event metadata for their own call.
        // The separate /api/msa-monitor remains staff/operator-only and never
        // issues an observer audio token to guest callers.
        if (action.action === "activity") {
          if (!guest || process.env["VAB_PUBLIC_GUEST_ACTIVITY_ENABLED"] !== "true")
            return json({ error: "forbidden" }, 403);
          const scope = guestActivityScope(request, action.voice_session_id);
          if (!scope) return json({ error: "forbidden" }, 403);
          const key = process.env["VAB_CALL_ACTIVITY_SERVICE_KEY"] ?? "";
          if (key.length < 32 || key === cfg.serviceKey)
            return json({ error: "activity_unavailable" }, 503);
          try {
            const cursor = action.cursor ? `?cursor=${encodeURIComponent(action.cursor)}` : "";
            const result = await fetch(
              cfg.baseUrl +
                `/api/voice-sessions/${encodeURIComponent(action.voice_session_id)}/caller-activity-events` +
                cursor,
              {
                method: "GET",
                headers: {
                  Authorization: `Bearer ${key}`,
                  "X-Demo-Role": "SCHEDULER",
                  "X-Demo-Actor": "synthetic-caller-activity-projection",
                  "X-Demo-Case": scope.caseId,
                  Accept: "application/json",
                },
                redirect: "error",
                signal: AbortSignal.timeout(10000),
                cache: "no-store",
              },
            );
            if (!result.ok) return json({ error: "activity_unavailable" }, 503);
            const projected = projectCallerActivityPage(await result.json(), {
              voiceSessionId: action.voice_session_id,
              caseId: scope.caseId,
              interactionId: scope.interactionId,
              correlationId: scope.correlationId,
            });
            if (!projected) return json({ error: "activity_contract_invalid" }, 502);
            return json(projected, 200);
          } catch {
            return json({ error: "activity_unavailable" }, 503);
          }
        }

        // Guest code cannot reach monitor operations. Restrict each lifecycle
        // update to a short-lived, per-call token returned by this BFF.
        if (
          guest &&
          (action.action === "connected" || action.action === "end" || action.action === "renew") &&
          !verifyGuestSession(request, action.voice_session_id, action.action === "end")
        )
          return json({ error: "forbidden" }, 403);
        let guestStartReserved = false;
        try {
          if (action.action === "status") {
            const status = await callBackend(cfg, "/api/voice/status", INTAKE_CASE_ID);
            const transport = isMap(status.transport) ? status.transport : {};
            return json(
              {
                synthetic: true,
                backend_connected: true,
                browser_softphone_enabled: transport.browser_softphone_enabled === true,
              },
              200,
            );
          }

          if (action.action === "start") {
            const status = await callBackend(cfg, "/api/voice/status", INTAKE_CASE_ID);
            if (!isMap(status.transport) || status.transport.browser_softphone_enabled !== true)
              return json({ error: "voice_gateway_not_ready" }, 503);

            if (guest) {
              if (!reserveGuestStart()) return json({ error: "guest_call_limit_reached" }, 429);
              guestStartReserved = true;
            }

            const encounter = await callBackend(
              cfg,
              `/api/scheduling-encounters/${encodeURIComponent(INTAKE_CASE_ID)}`,
              INTAKE_CASE_ID,
            );
            const schedulingEncounterId = str(encounter.scheduling_encounter_id);
            if (!schedulingEncounterId || encounter.case_id !== INTAKE_CASE_ID)
              throw new Error("encounter_contract");

            const interaction = await callBackend(
              cfg,
              "/api/interactions",
              INTAKE_CASE_ID,
              "POST",
              {
                case_id: INTAKE_CASE_ID,
                scheduling_encounter_id: schedulingEncounterId,
                channel: "PHONE",
                agent_opening: true,
              },
            );
            const interactionId = str(interaction.interaction_id);
            const correlationId = str(interaction.correlation_id);
            if (
              !interactionId ||
              !correlationId ||
              interaction.case_id !== INTAKE_CASE_ID ||
              interaction.runtime_failure_code
            )
              throw new Error("interaction_contract");

            const session = await callBackend(cfg, "/api/voice-sessions", INTAKE_CASE_ID, "POST", {
              interaction_id: interactionId,
              correlation_id: correlationId,
              case_id: INTAKE_CASE_ID,
              scheduling_encounter_id: schedulingEncounterId,
              transport: "LIVEKIT_WEBRTC",
            });
            const voiceSessionId = str(session.voice_session_id);
            if (!voiceSessionId || session.case_id !== INTAKE_CASE_ID)
              throw new Error("session_contract");

            const token = await callBackend(
              cfg,
              `/api/voice-sessions/${encodeURIComponent(voiceSessionId)}/webrtc-token`,
              INTAKE_CASE_ID,
              "POST",
              {},
            );
            const media = validateMediaToken(token, voiceSessionId);
            if (!media) throw new Error("media_contract");
            const {
              server_url: serverUrl,
              participant_token: participantToken,
              room_name: roomName,
            } = media;
            const guestToken = guest
              ? registerGuestSession(voiceSessionId, {
                  caseId: INTAKE_CASE_ID,
                  interactionId,
                  correlationId,
                })
              : null;
            guestStartReserved = false;
            return json(
              {
                synthetic: true,
                ...(guestToken
                  ? {
                      guest_call_token: guestToken,
                      guest_expires_at: guestSessionDeadline(guestToken),
                    }
                  : {}),
                case_id: INTAKE_CASE_ID,
                interaction_id: interactionId,
                voice_session_id: voiceSessionId,
                room_name: roomName,
                server_url: serverUrl,
                participant_token: participantToken,
                correlation_id: correlationId,
              },
              200,
            );
          }

          // Only an existing, backend-owned session may receive lifecycle events.
          const session = await callBackend(
            cfg,
            `/api/voice-sessions/${encodeURIComponent(action.voice_session_id)}`,
            INTAKE_CASE_ID,
          );
          if (
            session.case_id !== INTAKE_CASE_ID ||
            session.voice_session_id !== action.voice_session_id
          )
            return json({ error: "session_scope_mismatch" }, 403);

          if (action.action === "renew") {
            const renewed = await callBackend(
              cfg,
              `/api/voice-sessions/${encodeURIComponent(action.voice_session_id)}/renew`,
              INTAKE_CASE_ID,
              "POST",
              {},
            );
            if (renewed["ok"] !== true || renewed.voice_session_id !== action.voice_session_id)
              return json({ error: "call_renewal_denied" }, 403);
            const deadline = guest ? renewGuestSession(request, action.voice_session_id) : null;
            if (guest && deadline === null) return json({ error: "call_renewal_denied" }, 403);
            return json({ ok: true, guest_expires_at: deadline }, 200);
          }

          const lifecycle = await callBackend(
            cfg,
            `/api/voice-sessions/${encodeURIComponent(action.voice_session_id)}/events`,
            INTAKE_CASE_ID,
            "POST",
            {
              event_type: action.action === "connected" ? "CONNECTED" : "SESSION_ENDED",
              ...(action.action === "connected"
                ? {
                    provider_session_id: `vab-${action.voice_session_id}`,
                    payload: { provider: "LIVEKIT" },
                  }
                : {
                    provider_event_id: `end-${action.voice_session_id}`,
                    payload: { end_reason: action.reason ?? "CALLER_ENDED" },
                  }),
            },
          );
          return json(
            {
              ok: true,
              synthetic: true,
              ...(action.action === "end"
                ? {
                    after_call: projectAfterCall(lifecycle["after_call"]) ?? {
                      status: "UNAVAILABLE",
                      persisted: false,
                    },
                  }
                : {}),
            },
            200,
          );
        } catch (error) {
          if (guestStartReserved) failGuestStart();
          if (error instanceof Error && error.message === "upstream_503")
            return json({ error: "avery_or_backend_not_ready" }, 503);
          if (error instanceof Error && error.message === "upstream_404")
            return json({ error: "unknown_backend_case_or_session" }, 404);
          return json({ error: "backend_call_failed" }, 502);
        }
      },
    },
  },
});
