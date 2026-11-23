import test from "node:test";
import assert from "node:assert/strict";
import { readOptions, runSmoke } from "./smoke-msa-monitor.mjs";

const env = {
  VAB_RUN_MSA_MONITOR_SMOKE: "1",
  VAB_MSA_FRONTEND_URL: "http://127.0.0.1:5173",
  VAB_MSA_OPERATOR_ACCESS_CODE: "o".repeat(40),
  VAB_MSA_MONITOR_SERVICE_KEY: "s".repeat(40),
  VAB_MSA_TEST_CASE_ID: "DEMO-PC-5000999-001",
  VAB_MSA_TEST_VOICE_SESSION_ID: "vs-sandbox-test",
};

const response = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function token(overrides = {}, grants = {}, claimsOverride = {}) {
  const claims = {
    exp: Math.floor(Date.now() / 1000) + 120,
    nbf: Math.floor(Date.now() / 1000) - 5,
    video: {
      roomJoin: true,
      canSubscribe: true,
      canPublish: false,
      canPublishData: false,
      room: "vab-vs-sandbox-test",
      ...grants,
    },
    ...claimsOverride,
  };
  const jwt = [
    Buffer.from("{}").toString("base64url"),
    Buffer.from(JSON.stringify(claims)).toString("base64url"),
    Buffer.from("sig").toString("base64url"),
  ].join(".");
  return {
    synthetic: true,
    capability: "subscribe_only",
    case_id: env.VAB_MSA_TEST_CASE_ID,
    voice_session_id: env.VAB_MSA_TEST_VOICE_SESSION_ID,
    room_name: "vab-vs-sandbox-test",
    interaction_id: "int-1",
    participant_token: jwt,
    server_url: "ws://127.0.0.1:7880",
    expires_in_seconds: 120,
    ...overrides,
  };
}

const page = (events = [], overrides = {}) => ({
  case_id: env.VAB_MSA_TEST_CASE_ID,
  interaction_id: "int-1",
  correlation_id: "corr-1",
  scheduling_encounter_id: "SE-1",
  synthetic: true,
  transcript_verified: false,
  media_connected: false,
  events,
  ...overrides,
});

function fakeFetch(tokenResponse, eventsResponse) {
  const calls = [];
  const requester = async (url, init) => {
    assert.equal(url, env.VAB_MSA_FRONTEND_URL + "/api/msa-monitor");
    assert.equal(init.method, "POST");
    assert.equal(init.headers.Authorization, "Bearer " + env.VAB_MSA_OPERATOR_ACCESS_CODE);
    const body = JSON.parse(init.body);
    calls.push(body.action);
    if (body.action === "token") return tokenResponse;
    if (body.action === "events") return eventsResponse;
    throw new Error("Unexpected action");
  };
  return { requester, calls };
}

test("requires local opt-in, synthetic case, strong distinct operator code and local origin", () => {
  assert.throws(() => readOptions({}, "before"), /Opt in/);
  assert.throws(() => readOptions(env, "other"), /Phase/);
  assert.throws(
    () => readOptions({ ...env, VAB_MSA_FRONTEND_URL: "https://example.com" }, "before"),
    /localhost/,
  );
  assert.throws(
    () => readOptions({ ...env, VAB_MSA_TEST_CASE_ID: "patient-123" }, "before"),
    /synthetic DEMO/,
  );
  assert.throws(
    () =>
      readOptions(
        { ...env, VAB_MSA_OPERATOR_ACCESS_CODE: env.VAB_MSA_MONITOR_SERVICE_KEY },
        "before",
      ),
    /distinct/,
  );
  assert.equal(readOptions(env, "ready").url, "http://127.0.0.1:5173");
});

test("before call: 409 room-not-ready never returns a token or invokes event poll", async () => {
  const mock = fakeFetch(response({ error: "voice_room_not_ready" }, 409));
  const result = await runSmoke("before", env, mock.requester);
  assert.deepEqual(result, { phase: "before", observer_token_issued: false, room_ready: false });
  assert.deepEqual(mock.calls, ["token"]);
});

test("before call: 200 token is a failure, not silently accepted", async () => {
  const mock = fakeFetch(response(token()));
  await assert.rejects(() => runSmoke("before", env, mock.requester), /fail closed/);
  assert.deepEqual(mock.calls, ["token"]);
});

test("ready: read-only JWT and sanitized case-scoped events succeed without media claim", async () => {
  const mock = fakeFetch(
    response(token()),
    response(
      page([
        {
          event_id: "evt-1",
          event_type: "mcp_tool_called",
          synthetic: true,
          case_id: env.VAB_MSA_TEST_CASE_ID,
          interaction_id: "int-1",
          correlation_id: "corr-1",
          scheduling_encounter_id: "SE-1",
          payload: { tool_name: "search_availability", tool_call_id: "call-1" },
        },
        {
          event_id: "evt-2",
          event_type: "mcp_tool_result",
          synthetic: true,
          case_id: env.VAB_MSA_TEST_CASE_ID,
          interaction_id: "int-1",
          correlation_id: "corr-1",
          scheduling_encounter_id: "SE-1",
          payload: { tool_name: "search_availability", status: "completed" },
        },
      ]),
    ),
  );
  const result = await runSmoke("ready", env, mock.requester);
  assert.deepEqual(result, {
    phase: "ready",
    observer_token_read_only: true,
    event_feed_case_scoped: true,
    event_count: 2,
    mcp_event_count: 2,
    media_tracks_verified: false,
  });
  assert(!JSON.stringify(result).includes("participant_token"));
  assert.deepEqual(mock.calls, ["token", "events"]);
});

test("ready: unsafe publish grant, wrong case and raw tool input fail closed", async () => {
  for (const bad of [
    token({ case_id: "OTHER-CASE" }),
    token({}, { canPublish: true }),
    token({ server_url: undefined }),
    token({ server_url: "https://invalid.example" }),
    token({ server_url: "wss://" }),
    token({ expires_in_seconds: -1 }),
    token({ interaction_id: "x".repeat(65) }),
    token({}, {}, { exp: 1 }),
    token({}, {}, { nbf: Math.floor(Date.now() / 1000) + 3600 }),
  ]) {
    const mock = fakeFetch(response(bad), response(page()));
    await assert.rejects(() => runSmoke("ready", env, mock.requester));
    assert.deepEqual(mock.calls, ["token"]);
  }
  const ev = {
    event_id: "evt-1",
    synthetic: true,
    event_type: "mcp_tool_result",
    case_id: env.VAB_MSA_TEST_CASE_ID,
    interaction_id: "int-1",
    correlation_id: "corr-1",
    scheduling_encounter_id: "SE-1",
    payload: { tool_name: "search_availability", result: { name: "must not leak" } },
  };
  const mock = fakeFetch(response(token()), response(page([ev])));
  await assert.rejects(() => runSmoke("ready", env, mock.requester), /Unsafe event payload/);

  const nested = {
    ...ev,
    payload: { status: { raw_result: { patient: "sensitive" } } },
  };
  await assert.rejects(
    () => runSmoke("ready", env, fakeFetch(response(token()), response(page([nested]))).requester),
    /Unsafe tool metadata value/,
  );

  const transcript = {
    ...ev,
    event_type: "veteran_utterance",
    payload: { transcript_available: "no" },
  };
  await assert.rejects(
    () =>
      runSmoke("ready", env, fakeFetch(response(token()), response(page([transcript]))).requester),
    /Unsafe speech metadata value/,
  );

  const missingType = { ...ev, payload: {} };
  delete missingType.event_type;
  await assert.rejects(
    () =>
      runSmoke("ready", env, fakeFetch(response(token()), response(page([missingType]))).requester),
    /Unsafe event envelope metadata/,
  );

  const unsafeEnvelope = { ...ev, payload: {}, raw_result: { patient: "sensitive" } };
  await assert.rejects(
    () =>
      runSmoke(
        "ready",
        env,
        fakeFetch(response(token()), response(page([unsafeEnvelope]))).requester,
      ),
    /Unsafe event envelope/,
  );
  const unsafePage = page([], { raw_result: { patient: "sensitive" } });
  await assert.rejects(
    () => runSmoke("ready", env, fakeFetch(response(token()), response(unsafePage)).requester),
    /Unsafe event page envelope/,
  );
});

test("ready: stale case/correlation and unavailable room are not reported successful", async () => {
  const wrong = fakeFetch(response(token()), response(page([], { correlation_id: "" })));
  await assert.rejects(() => runSmoke("ready", env, wrong.requester), /correlation ID/);
  const stale = fakeFetch(response(token()), response(page([], { case_id: "OTHER-CASE" })));
  await assert.rejects(() => runSmoke("ready", env, stale.requester), /does not match/);
  const noRoom = fakeFetch(response({ error: "voice_room_not_ready" }, 409));
  await assert.rejects(() => runSmoke("ready", env, noRoom.requester), /Avery dispatch/);
  const offline = fakeFetch(response({ error: "voice_room_readiness_unavailable" }, 503));
  await assert.rejects(
    () => runSmoke("ready", env, offline.requester),
    /LiveKit readiness unavailable/,
  );
});
