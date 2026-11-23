import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyEventsPage,
  classifyParticipant,
  emptyProjection,
  validateToken,
} from "@/lib/live-monitor";
import {
  backendRequest,
  bearer,
  parseGatewayBody,
  projectMonitorBackendFailure,
  readGatewayConfig,
  timingSafeEqualText,
} from "@/lib/msa-monitor-gateway";

const K = "k".repeat(32);
const C = "c".repeat(32);
const env = {
  VAB_MSA_LIVE_MONITOR_ENABLED: "true",
  VAB_MSA_MONITOR_SERVICE_KEY: K,
  VAB_MSA_OPERATOR_ACCESS_CODE: C,
  VAB_API_BASE_URL: "https://api.example.test",
};
const ev = (id: string, over: Record<string, unknown> = {}) => ({
  event_id: id,
  event_type: "mcp.tool.completed",
  interaction_id: "int-1",
  case_id: "case-1",
  scheduling_encounter_id: "enc-1",
  correlation_id: "cor-1",
  source: "mcp",
  occurred_at: "2026-11-09T17:00:00Z",
  synthetic: true,
  payload: { tool_name: "get_availability", status: "completed", raw_args: { dob: "x" } },
  ...over,
});
const page = (events: unknown[], over: Record<string, unknown> = {}) => ({
  interaction_id: "int-1",
  case_id: "case-1",
  scheduling_encounter_id: "enc-1",
  correlation_id: "cor-1",
  status: "active",
  human_control_mode: "observe",
  events,
  next_cursor: "c2",
  synthetic: true,
  transcript_verified: false,
  media_connected: false,
  ...over,
});

describe("event projection", () => {
  const base = emptyProjection("int-1", "case-1");
  it("rejects wrong case, interaction and correlation", () => {
    expect(applyEventsPage(base, page([], { case_id: "case-2" }))).toMatchObject({
      ok: false,
      reason: "wrong_case",
    });
    expect(applyEventsPage(base, page([ev("e1", { case_id: "case-2" })]))).toMatchObject({
      ok: false,
      reason: "wrong_case",
    });
    expect(applyEventsPage(base, page([ev("e1", { interaction_id: "x" })]))).toMatchObject({
      ok: false,
    });
    expect(applyEventsPage(base, page([ev("e1", { correlation_id: "cor-2" })]))).toMatchObject({
      ok: false,
      reason: "wrong_correlation",
    });
    const first = applyEventsPage(base, page([ev("e1")]));
    if (!first.ok) throw new Error();
    expect(applyEventsPage(first.state, page([], { correlation_id: "cor-9" }))).toMatchObject({
      ok: false,
      reason: "wrong_correlation",
    });
  });
  it("dedups by event_id and strips raw payload fields", () => {
    const a = applyEventsPage(base, page([ev("e1"), ev("e1")]));
    if (!a.ok) throw new Error();
    const b = applyEventsPage(a.state, page([ev("e1"), ev("e2")]));
    if (!b.ok) throw new Error();
    expect(b.state.events.map((e) => e.event_id)).toEqual(["e1", "e2"]);
    expect(JSON.stringify(b.state)).not.toContain("dob");
    expect(b.state.transcript_verified).toBe(false);
    expect(b.state.cursor).toBe("c2");
  });
  it("preserves only a literal verified identity boolean from a result event", () => {
    const rejected = applyEventsPage(
      base,
      page([
        ev("denied", {
          event_type: "mcp_tool_result",
          payload: {
            tool_name: "verify_synthetic_identity",
            tool_call_id: "call-identity",
            status: "completed",
            verified: false,
            raw_result: { name: "DO_NOT_LEAK" },
          },
        }),
      ]),
    );
    if (!rejected.ok) throw new Error("failed to project denied result");
    expect(rejected.state.events[0]?.verified).toBe(false);
    expect(JSON.stringify(rejected.state)).not.toContain("DO_NOT_LEAK");

    const accepted = applyEventsPage(
      base,
      page([
        ev("accepted", {
          event_type: "mcp_tool_result",
          payload: {
            tool_name: "verify_synthetic_identity",
            status: "completed",
            verified: true,
          },
        }),
      ]),
    );
    if (!accepted.ok) throw new Error("failed to project verified result");
    expect(accepted.state.events[0]?.verified).toBe(true);

    const untrusted = applyEventsPage(
      base,
      page([
        ev("wrong-tool", {
          event_type: "mcp_tool_result",
          payload: { tool_name: "search_availability", verified: true },
        }),
      ]),
    );
    if (!untrusted.ok) throw new Error("failed to project other tool");
    expect(untrusted.state.events[0]?.verified).toBeUndefined();
  });
  it("token must be subscribe-only, synthetic and case/session bound", () => {
    const t = {
      server_url: "wss://lk.example.test",
      participant_token: "tok",
      voice_session_id: "vs-1",
      interaction_id: "int-1",
      case_id: "case-1",
      room_name: "room",
      capability: "subscribe_only",
      synthetic: true,
      expires_in_seconds: 120,
    };
    const exp = { case_id: "case-1", voice_session_id: "vs-1" };
    expect(validateToken(t, exp)).not.toBeNull();
    expect(validateToken({ ...t, capability: "publish" }, exp)).toBeNull();
    expect(validateToken({ ...t, case_id: "case-2" }, exp)).toBeNull();
    expect(validateToken({ ...t, synthetic: false }, exp)).toBeNull();
  });
  it("unknown participants stay unknown", () => {
    expect(classifyParticipant({ metadata: "" })).toBe("unknown");
    expect(classifyParticipant({ isAgent: true })).toBe("agent");
    expect(classifyParticipant({ metadata: '{"vab_role":"veteran_caller"}' })).toBe("caller");
  });
});

describe("observer-first readiness error projection", () => {
  const token = { action: "token", case_id: "case-1", voice_session_id: "vs-1" } as const;
  const events = { action: "events", case_id: "case-1", interaction_id: "int-1" } as const;

  it("keeps only allowlisted readiness errors, not raw backend errors", () => {
    expect(projectMonitorBackendFailure(token, 409, "voice_room_not_ready")).toEqual({
      status: 409,
      body: { error: "voice_room_not_ready" },
    });
    expect(projectMonitorBackendFailure(token, 503, "voice_room_readiness_unavailable")).toEqual({
      status: 503,
      body: { error: "voice_room_readiness_unavailable" },
    });
    expect(projectMonitorBackendFailure(token, 409, "private-unknown")).toEqual({
      status: 502,
      body: { error: "backend_rejected", status: 409 },
    });
    expect(projectMonitorBackendFailure(events, 409, "voice_room_not_ready")).toEqual({
      status: 502,
      body: { error: "backend_rejected", status: 409 },
    });
    expect(
      JSON.stringify(projectMonitorBackendFailure(token, 503, "private-credentials")),
    ).not.toContain("private-credentials");
  });
});

describe("server gateway gate", () => {
  it("fails closed on every missing/weak setting", () => {
    expect(readGatewayConfig(env)).not.toBeNull();
    expect(readGatewayConfig({ ...env, VAB_MSA_LIVE_MONITOR_ENABLED: undefined })).toBeNull();
    expect(readGatewayConfig({ ...env, VAB_MSA_MONITOR_SERVICE_KEY: "short" })).toBeNull();
    expect(readGatewayConfig({ ...env, VAB_MSA_OPERATOR_ACCESS_CODE: "short" })).toBeNull();
    expect(readGatewayConfig({ ...env, VAB_MSA_OPERATOR_ACCESS_CODE: K })).toBeNull();
    expect(readGatewayConfig({ ...env, VAB_API_BASE_URL: "http://api.example.test" })).toBeNull();
    expect(readGatewayConfig({ ...env, VAB_API_BASE_URL: "http://localhost:8000" })).not.toBeNull();
  });
  it("compares operator code and validates actions strictly", async () => {
    expect(await timingSafeEqualText(C, C)).toBe(true);
    expect(await timingSafeEqualText(C + "x", C)).toBe(false);
    expect(bearer(`Bearer ${C}`)).toBe(C);
    expect(bearer("Basic x")).toBeNull();
    expect(
      parseGatewayBody({ action: "token", case_id: "../x", voice_session_id: "v" }),
    ).toBeNull();
    expect(parseGatewayBody({ action: "delete", case_id: "c" })).toBeNull();
    expect(
      parseGatewayBody({ action: "events", case_id: "c", interaction_id: "i", cursor: "a/b" }),
    ).toBeNull();
    const cfg = readGatewayConfig(env)!;
    const req = backendRequest(cfg, {
      action: "events",
      case_id: "c",
      interaction_id: "i",
      cursor: "z",
    });
    expect(req.url).toBe("https://api.example.test/api/interactions/i/msa-monitor-events?cursor=z");
    expect(req.init.headers["X-Demo-Role"]).toBe("SCHEDULER");
    expect(req.init.headers["X-Demo-Case"]).toBe("c");
  });
});

// ---- hook: read-only observer, unsubscribe/reconnect ----
const roomState = vi.hoisted(() => ({
  handlers: {} as Record<string, (...a: unknown[]) => void>,
  connectArgs: [] as unknown[],
  disconnected: 0,
  startAudioFails: false,
  startAudioCalls: 0,
}));
vi.mock("livekit-client", () => {
  class Room {
    on(name: string, fn: (...a: unknown[]) => void) {
      roomState.handlers[name] = fn;
      return this;
    }
    async connect(...args: unknown[]) {
      roomState.connectArgs = args;
    }
    async disconnect() {
      roomState.disconnected++;
    }
    async startAudio() {
      if (roomState.startAudioFails) throw new Error("NotAllowedError");
      roomState.startAudioCalls++;
    }
    localParticipant = { publishTrack: vi.fn(), setMicrophoneEnabled: vi.fn() };
  }
  return {
    Room,
    RoomEvent: {
      Connected: "connected",
      Reconnecting: "reconnecting",
      Reconnected: "reconnected",
      Disconnected: "disconnected",
      TrackSubscribed: "trackSubscribed",
      TrackUnsubscribed: "trackUnsubscribed",
      ParticipantDisconnected: "participantDisconnected",
    },
    Track: { Kind: { Audio: "audio" } },
    ParticipantKind: { AGENT: 4 },
  };
});

const fire = (name: string, ...a: unknown[]) => roomState.handlers[name]?.(...a);
describe("useLiveMonitor", () => {
  beforeEach(() => {
    roomState.handlers = {};
    roomState.disconnected = 0;
    roomState.startAudioFails = false;
    roomState.startAudioCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        const data =
          body.action === "token"
            ? {
                server_url: "wss://lk.example.test",
                participant_token: "tok",
                voice_session_id: "vs-1",
                interaction_id: "int-1",
                case_id: "case-1",
                room_name: "room",
                capability: "subscribe_only",
                synthetic: true,
                expires_in_seconds: 120,
              }
            : page([ev("e1")]);
        return new Response(JSON.stringify(data), { status: 200 });
      }),
    );
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("connected only after RoomEvent.Connected, tracks unsubscribe/reconnect, never publishes", async () => {
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result, unmount } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    expect(result.current.phase).toBe("connecting");
    expect(roomState.connectArgs[2]).toMatchObject({ autoSubscribe: true });
    act(() => fire("connected"));
    expect(result.current.phase).toBe("connected");
    const track = { kind: "audio", detach: () => [] };
    act(() => fire("trackSubscribed", track, {}, { kind: 4, metadata: "" }));
    expect(result.current.agentTrack).toBe(track);
    const stranger = { kind: "audio", detach: () => [] };
    act(() => fire("trackSubscribed", stranger, {}, { kind: 0, metadata: "" }));
    expect(result.current.callerTrack).toBeNull();
    act(() => fire("trackUnsubscribed", track));
    expect(result.current.agentTrack).toBeNull();
    act(() => fire("reconnecting"));
    expect(result.current.phase).toBe("reconnecting");
    act(() => fire("reconnected"));
    expect(result.current.phase).toBe("connected");
    await waitFor(() => expect(result.current.projection?.events.length).toBe(1));
    const calls = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
    expect(calls.every(([u]) => u === "/api/msa-monitor")).toBe(true);
    unmount();
    expect(roomState.disconnected).toBe(1);
  });

  const mkTrack = () => {
    const els: HTMLAudioElement[] = [];
    return {
      kind: "audio",
      attachCalls: 0,
      els,
      attach() {
        this.attachCalls++;
        const el = document.createElement("audio");
        els.push(el);
        return el;
      },
      detach: vi.fn((el?: HTMLAudioElement) => (el ? [el] : els)),
    };
  };
  const audioCount = () => document.querySelectorAll("audio").length;

  it("Monitor clicked before subscription plays late tracks once and cleans up", async () => {
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result, unmount } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    act(() => fire("connected"));
    // No audio output before gesture, even when a track is subscribed.
    const early = mkTrack();
    act(() => fire("trackSubscribed", early, {}, { kind: 4, metadata: "" }));
    expect(early.attachCalls).toBe(0);
    act(() => fire("trackUnsubscribed", early));
    expect(roomState.startAudioCalls).toBe(0);

    await act(async () => {
      await result.current.setMonitoring(true);
    });
    expect(result.current.monitoring).toBe(true);
    expect(roomState.startAudioCalls).toBe(1);
    expect(audioCount()).toBe(0);

    const agent = mkTrack();
    const caller = mkTrack();
    act(() => fire("trackSubscribed", agent, {}, { kind: 4, metadata: "" }));
    act(() =>
      fire("trackSubscribed", caller, {}, { kind: 0, metadata: '{"vab_role":"veteran_caller"}' }),
    );
    const stranger = mkTrack();
    act(() => fire("trackSubscribed", stranger, {}, { kind: 0, metadata: "{}" }));
    expect(agent.attachCalls).toBe(1);
    expect(caller.attachCalls).toBe(1);
    expect(stranger.attachCalls).toBe(0);
    expect(audioCount()).toBe(2);

    // Replacement detaches old, attaches new exactly once.
    const agent2 = mkTrack();
    act(() => fire("trackSubscribed", agent2, {}, { kind: 4, metadata: "" }));
    expect(agent.detach).toHaveBeenCalled();
    expect(agent2.attachCalls).toBe(1);
    expect(caller.attachCalls).toBe(1);
    expect(audioCount()).toBe(2);

    act(() => fire("trackUnsubscribed", caller));
    expect(audioCount()).toBe(1);

    await act(async () => {
      await result.current.setMonitoring(false);
    });
    expect(audioCount()).toBe(0);
    await act(async () => {
      await result.current.setMonitoring(true);
    });
    expect(agent2.attachCalls).toBe(2);
    expect(audioCount()).toBe(1);
    unmount();
    expect(audioCount()).toBe(0);
    expect(roomState.disconnected).toBe(1);
  });

  it("startAudio failure keeps monitoring off with no playback", async () => {
    roomState.startAudioFails = true;
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    act(() => fire("connected"));
    const agent = mkTrack();
    act(() => fire("trackSubscribed", agent, {}, { kind: 4, metadata: "" }));
    await act(async () => {
      await result.current.setMonitoring(true);
    });
    expect(result.current.monitoring).toBe(false);
    expect(agent.attachCalls).toBe(0);
    expect(audioCount()).toBe(0);
    expect(result.current.phase).toBe("connected");
  });

  it("409 explains Veteran-first start, keeps monitor disconnected and allows a retry", async () => {
    roomState.connectArgs = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: "voice_room_not_ready" }), { status: 409 }),
      ),
    );
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/start the synthetic veteran call/i);
    expect(result.current.projection).toBeNull();
    expect(roomState.connectArgs).toEqual([]);
  });

  it("503 readiness failure cannot connect and does not leak provider error details", async () => {
    roomState.connectArgs = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: "voice_room_readiness_unavailable" }), {
            status: 503,
          }),
      ),
    );
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/livekit readiness unavailable/i);
    expect(result.current.projection).toBeNull();
    expect(roomState.connectArgs).toEqual([]);
  });

  it("gateway 403 fails closed into error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 403 })),
    );
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result } = renderHook(() => useLiveMonitor());
    await act(async () => {
      await result.current.connect({ accessCode: C, caseId: "case-1", voiceSessionId: "vs-1" });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.projection).toBeNull();
  });
});

describe("shell default", () => {
  it("defaults to an honest disconnected live observer, not simulated listening", async () => {
    vi.doMock("@tanstack/react-router", () => ({
      Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
      ClientOnly: ({ fallback }: { fallback: React.ReactNode }) => <>{fallback}</>,
    }));
    HTMLElement.prototype.scrollTo = vi.fn();
    const { MSAAppShell } = await import("@/components/msa/app-shell");
    render(<MSAAppShell />);
    expect(screen.getByText(/SANDBOX · Live observer · LiveKit not connected/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect sandbox…" })).toBeInTheDocument();
    expect(
      screen.getByText("Voice transcript unavailable from authoritative source"),
    ).toBeInTheDocument();
    expect(screen.getByText("Awaiting live caller audio")).toBeInTheDocument();
    expect(screen.queryByText(/Scripted replay · NO LiveKit audio connection/)).toBeNull();
    expect(screen.queryByText(/Simulated booking completed/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Play replay" })).toBeNull();
  });
});
