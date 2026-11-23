#!/usr/bin/env node
/**
 * Read-only Command Center ↔ VAB sandbox handshake smoke check.
 *
 * Does not create interactions, rooms, agents, participants, bookings or MCP
 * writes; it never prints JWTs, access codes, patient fields or event payloads.
 * Must be run on the same local host as the frontend BFF, after a canonical
 * synthetic voice session was created through the existing VAB application.
 *
 * Usage: VAB_RUN_MSA_MONITOR_SMOKE=1 node scripts/smoke-msa-monitor.mjs before
 *        VAB_RUN_MSA_MONITOR_SMOKE=1 node scripts/smoke-msa-monitor.mjs ready
 */

import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ID = /^[A-Za-z0-9_-]{1,64}$/;
const allowedHost = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function readOptions(env, phase) {
  if (env.VAB_RUN_MSA_MONITOR_SMOKE !== "1") {
    throw new Error("Opt in with VAB_RUN_MSA_MONITOR_SMOKE=1 (local synthetic only).");
  }
  if (phase !== "before" && phase !== "ready") {
    throw new Error("Phase must be 'before' (no caller) or 'ready' (Veteran and Avery active).");
  }
  const url = new URL(env.VAB_MSA_FRONTEND_URL || "http://127.0.0.1:5173");
  if (
    !allowedHost.has(url.hostname) ||
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("Frontend URL must be an unadorned localhost origin.");
  }
  const caseId = env.VAB_MSA_TEST_CASE_ID;
  const sessionId = env.VAB_MSA_TEST_VOICE_SESSION_ID;
  const accessCode = env.VAB_MSA_OPERATOR_ACCESS_CODE;
  if (!ID.test(caseId ?? "") || !caseId.startsWith("DEMO-")) {
    throw new Error("Provide a synthetic DEMO-* case ID (VAB_MSA_TEST_CASE_ID).");
  }
  if (!ID.test(sessionId ?? "")) {
    throw new Error("Provide a registered synthetic voice session ID.");
  }
  if (
    typeof accessCode !== "string" ||
    accessCode.length < 32 ||
    accessCode === env.VAB_MSA_MONITOR_SERVICE_KEY
  ) {
    throw new Error("Provide a distinct strong local operator code (32+ characters).");
  }
  return { url: url.origin, caseId, sessionId, accessCode, phase };
}

async function readJsonSafely(response) {
  try {
    const value = await response.json();
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value;
    }
  } catch {
    // Invalid JSON always fails closed.
  }
  return {};
}

function assert(condition, description) {
  if (!condition) throw new Error(description);
}

function inspectClaims(jwt) {
  const parts = jwt.split(".");
  assert(parts.length === 3, "Observer token is not a JWT.");
  let claims;
  try {
    claims = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
  } catch {
    throw new Error("Observer JWT has invalid claims.");
  }
  const now = Math.floor(Date.now() / 1000);
  assert(
    Number.isInteger(claims?.exp) && claims.exp > now && claims.exp <= now + 3600,
    "Observer JWT is expired or has an unsafe expiration.",
  );
  assert(
    claims.nbf === undefined || (Number.isInteger(claims.nbf) && claims.nbf <= now),
    "Observer JWT is not valid yet.",
  );
  const grants = claims?.video;
  assert(
    grants?.roomJoin === true &&
      grants?.canSubscribe === true &&
      grants?.canPublish === false &&
      grants?.canPublishData === false,
    "Observer JWT contains unsafe publish or join grants.",
  );
  assert(typeof grants.room === "string", "Observer JWT has no room scope.");
  return grants.room;
}

function verifyEventPage(page, token) {
  const pageFields = new Set([
    "interaction_id",
    "case_id",
    "scheduling_encounter_id",
    "correlation_id",
    "status",
    "human_control_mode",
    "events",
    "next_cursor",
    "synthetic",
    "transcript_verified",
    "media_connected",
  ]);
  assert(
    Object.keys(page).every((key) => pageFields.has(key)),
    "Unsafe event page envelope.",
  );
  for (const key of ["status", "human_control_mode", "next_cursor"]) {
    const value = page[key];
    assert(
      value == null || (typeof value === "string" && value.length <= 128),
      "Unsafe event page metadata.",
    );
  }
  assert(page.case_id === token.case_id, "Event case does not match token.");
  assert(page.interaction_id === token.interaction_id, "Event interaction mismatch.");
  assert(page.synthetic === true, "Event feed is not synthetic.");
  assert(page.transcript_verified === false, "Unexpected transcript verification.");
  assert(page.media_connected === false, "Backend incorrectly asserted media connection.");
  assert(
    typeof page.correlation_id === "string" && page.correlation_id.length > 0,
    "Event correlation ID is missing.",
  );
  assert(
    typeof page.scheduling_encounter_id === "string" && page.scheduling_encounter_id.length > 0,
    "Encounter ID missing.",
  );
  assert(Array.isArray(page.events), "Event feed is missing event records.");
  let toolEvents = 0;
  const ids = new Set();
  const eventFields = new Set([
    "event_id",
    "event_type",
    "interaction_id",
    "case_id",
    "scheduling_encounter_id",
    "correlation_id",
    "source",
    "occurred_at",
    "synthetic",
    "payload",
  ]);
  for (const event of page.events) {
    assert(event && typeof event === "object" && !Array.isArray(event), "Invalid event envelope.");
    assert(
      Object.keys(event).every((key) => eventFields.has(key)),
      "Unsafe event envelope.",
    );
    for (const key of ["event_id", "event_type", "source", "occurred_at"]) {
      const value = event[key];
      assert(
        (key !== "event_type" && value === undefined) ||
          (typeof value === "string" && value.length >= 1 && value.length <= 128),
        "Unsafe event envelope metadata.",
      );
    }
    assert(
      event.case_id === token.case_id &&
        event.interaction_id === token.interaction_id &&
        event.correlation_id === page.correlation_id &&
        event.scheduling_encounter_id === page.scheduling_encounter_id &&
        event.synthetic === true,
      "Cross-case or cross-correlation event rejected.",
    );
    assert(typeof event.event_id === "string" && !ids.has(event.event_id), "Duplicate event ID.");
    ids.add(event.event_id);
    const p = event.payload ?? {};
    assert(p && typeof p === "object" && !Array.isArray(p), "Invalid event payload.");
    const fields = Object.keys(p);
    const isTool = ["mcp_tool_called", "mcp_tool_result"].includes(event.event_type);
    const allowed = isTool
      ? ["tool_name", "tool_call_id", "status", "error_code"]
      : ["transcript_available"];
    assert(
      fields.every((field) => allowed.includes(field)),
      "Unsafe event payload field.",
    );
    for (const field of fields) {
      const value = p[field];
      if (isTool) {
        assert(
          typeof value === "string" &&
            value.length >= 1 &&
            value.length <= 100 &&
            /^[A-Za-z0-9._:-]+$/.test(value),
          "Unsafe tool metadata value.",
        );
      } else {
        assert(
          field === "transcript_available" && value === false,
          "Unsafe speech metadata value.",
        );
      }
    }
    if (isTool) toolEvents++;
  }
  return { event_count: page.events.length, mcp_event_count: toolEvents };
}

export async function runSmoke(phase, env = process.env, requester = fetch) {
  const options = readOptions(env, phase);
  const post = async (body) => {
    const res = await requester(options.url + "/api/msa-monitor", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + options.accessCode,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    return { status: res.status, payload: await readJsonSafely(res) };
  };
  const tokenResult = await post({
    action: "token",
    case_id: options.caseId,
    voice_session_id: options.sessionId,
  });
  if (phase === "before") {
    assert(
      tokenResult.status === 409 &&
        tokenResult.payload.error === "voice_room_not_ready" &&
        !Object.hasOwn(tokenResult.payload, "participant_token"),
      "Observer-first preflight did not fail closed with 409. Check existing room, session and enabled gateways.",
    );
    return { phase: "before", observer_token_issued: false, room_ready: false };
  }
  if (tokenResult.status !== 200) {
    const code = tokenResult.payload.error;
    if (tokenResult.status === 409 && code === "voice_room_not_ready") {
      throw new Error(
        "Avery dispatch / connected Veteran not ready yet. Start the synthetic call first.",
      );
    }
    if (tokenResult.status === 503 && code === "voice_room_readiness_unavailable") {
      throw new Error("LiveKit readiness unavailable (503); no observer token issued.");
    }
    throw new Error(
      "Observer token gateway rejected the request (HTTP " + tokenResult.status + ").",
    );
  }
  const token = tokenResult.payload;
  assert(
    token.synthetic === true &&
      token.capability === "subscribe_only" &&
      token.case_id === options.caseId &&
      token.voice_session_id === options.sessionId &&
      token.room_name === "vab-" + options.sessionId &&
      typeof token.interaction_id === "string" &&
      token.interaction_id.length >= 1 &&
      token.interaction_id.length <= 64 &&
      typeof token.participant_token === "string" &&
      token.participant_token.length >= 1 &&
      token.participant_token.length <= 4096 &&
      typeof token.expires_in_seconds === "number" &&
      Number.isInteger(token.expires_in_seconds) &&
      token.expires_in_seconds > 0 &&
      token.expires_in_seconds <= 300 &&
      typeof token.server_url === "string" &&
      token.server_url.length >= 1 &&
      token.server_url.length <= 256 &&
      /^wss?:\/\//.test(token.server_url),
    "Observer token response is not browser-compatible and session-scoped.",
  );
  try {
    const signaling = new URL(token.server_url);
    assert(
      signaling.hostname && !signaling.username && !signaling.password,
      "Signaling URL is malformed.",
    );
  } catch {
    throw new Error("Signaling URL is malformed.");
  }
  assert(inspectClaims(token.participant_token) === token.room_name, "JWT room mismatch.");

  const eventResult = await post({
    action: "events",
    case_id: options.caseId,
    interaction_id: token.interaction_id,
  });
  assert(eventResult.status === 200, "Authoritative event feed unavailable.");
  const evidence = verifyEventPage(eventResult.payload, token);
  return {
    phase: "ready",
    observer_token_read_only: true,
    event_feed_case_scoped: true,
    ...evidence,
    media_tracks_verified: false,
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const phase = process.argv[2];
  try {
    const result = await runSmoke(phase);
    // This summary is safe: no JWT, access codes, event payloads or identifiers.
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    if (phase === "ready" && result.mcp_event_count === 0) {
      process.stdout.write("MCP event execution has not yet been observed.\n");
    }
    process.stdout.write("Live audio track and reconnect checks require the browser test.\n");
  } catch (error) {
    process.stderr.write(
      "FAIL: " + (error instanceof Error ? error.message : "Unexpected error") + "\n",
    );
    process.exitCode = 1;
  }
}
