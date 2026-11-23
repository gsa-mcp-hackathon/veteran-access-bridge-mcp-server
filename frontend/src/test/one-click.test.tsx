import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isTrustedOneClickRequest,
  oneClickConfig,
  authorizeSandboxRequest,
} from "@/lib/one-click-gate";
import { validateMediaToken } from "@/lib/demo-call-gateway";

const env = {
  VAB_MSA_LIVE_MONITOR_ENABLED: "true",
  VAB_MSA_ONE_CLICK_DEMO_ENABLED: "true",
  VAB_MSA_MONITOR_SERVICE_KEY: "k".repeat(32),
  VAB_MSA_OPERATOR_ACCESS_CODE: "c".repeat(32),
  VAB_API_BASE_URL: "http://127.0.0.1:8080",
  CODESPACE_NAME: "my-space-abc",
};
const local = {
  host: "localhost:5173",
  origin: "http://localhost:5173",
  secFetchSite: "same-origin",
};

const lk = vi.hoisted(() => ({ rooms: [] as { connect: ReturnType<typeof vi.fn> }[] }));
vi.mock("livekit-client", () => {
  class Room {
    handlers: Record<string, (...a: unknown[]) => void> = {};
    localParticipant = {
      setMicrophoneEnabled: vi.fn(async () => undefined),
      getTrackPublication: vi.fn(() => null),
      identity: "synthetic-browser-caller",
    };
    connect = vi.fn(async () => undefined);
    disconnect = vi.fn(async () => undefined);
    startAudio = vi.fn(async () => undefined);
    constructor() {
      lk.rooms.push(this);
    }
    on(e: string, f: (...a: unknown[]) => void) {
      this.handlers[e] = f;
      return this;
    }
  }
  return {
    Room,
    RoomEvent: {
      TrackSubscribed: "ts",
      TrackUnsubscribed: "tu",
      ActiveSpeakersChanged: "asp",
      Disconnected: "d",
    },
    ParticipantKind: { AGENT: "agent" },
    Track: { Kind: { Audio: "audio" }, Source: { Microphone: "microphone" } },
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  lk.rooms.length = 0;
});

describe("private one-click gate", () => {
  it("requires explicit opt-in, valid gateway config and a loopback backend", () => {
    expect(isTrustedOneClickRequest(env, local)).toBe(true);
    expect(
      isTrustedOneClickRequest({ ...env, VAB_MSA_ONE_CLICK_DEMO_ENABLED: undefined }, local),
    ).toBe(false);
    expect(isTrustedOneClickRequest({ ...env, VAB_MSA_LIVE_MONITOR_ENABLED: "false" }, local)).toBe(
      false,
    );
    expect(oneClickConfig({ ...env, VAB_API_BASE_URL: "https://api.example.test" })).toBeNull();
    expect(oneClickConfig({ ...env, VAB_MSA_OPERATOR_ACCESS_CODE: "k".repeat(32) })).toBeNull();
  });
  it("accepts only the current Codespace forwarding host over https", () => {
    const cs = "my-space-abc-5173.app.github.dev";
    expect(
      isTrustedOneClickRequest(env, { host: cs, origin: `https://${cs}`, secFetchSite: null }),
    ).toBe(true);
    expect(
      isTrustedOneClickRequest(env, { host: cs, origin: `http://${cs}`, secFetchSite: null }),
    ).toBe(false);
    const other = "other-space-5173.app.github.dev";
    expect(
      isTrustedOneClickRequest(env, {
        host: other,
        origin: `https://${other}`,
        secFetchSite: null,
      }),
    ).toBe(false);
  });
  it("rejects public preview, missing or cross-site origins", () => {
    const pub = "id-preview--x.lovable.app";
    expect(
      isTrustedOneClickRequest(env, {
        host: pub,
        origin: `https://${pub}`,
        secFetchSite: "same-origin",
      }),
    ).toBe(false);
    expect(isTrustedOneClickRequest(env, { ...local, origin: "https://evil.example" })).toBe(false);
    expect(isTrustedOneClickRequest(env, { ...local, origin: null })).toBe(false);
    expect(isTrustedOneClickRequest(env, { ...local, secFetchSite: "cross-site" })).toBe(false);
    expect(isTrustedOneClickRequest(env, { ...local, host: "localhost.evil.example" })).toBe(false);
  });
  it("keeps the operator-code path and rejects a wrong code even when trusted", async () => {
    const req = (h: Record<string, string>) =>
      new Request("http://localhost:5173/api/msa-monitor", { method: "POST", headers: h });
    expect(
      (
        await authorizeSandboxRequest(
          env,
          req({ host: "localhost:5173", origin: "http://localhost:5173" }),
        )
      ).ok,
    ).toBe(true);
    expect(
      (
        await authorizeSandboxRequest(
          env,
          req({
            authorization: `Bearer ${"c".repeat(32)}`,
            origin: "http://localhost:5173",
          }),
        )
      ).ok,
    ).toBe(true);
    expect(
      (
        await authorizeSandboxRequest(
          env,
          req({ authorization: `Bearer ${"c".repeat(32)}`, origin: "https://evil.example" }),
        )
      ).ok,
    ).toBe(false);
    expect(
      await authorizeSandboxRequest(
        env,
        req({
          authorization: "Bearer wrong",
          host: "localhost:5173",
          origin: "http://localhost:5173",
        }),
      ),
    ).toEqual({ ok: false, error: "forbidden" });
  });
});

describe("Lovable-hosted HTTPS call connection", () => {
  it("requires a strong demo access code, never unauthenticated hosted one-click", async () => {
    const hosted = {
      ...env,
      VAB_API_BASE_URL:
        "https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud",
      VAB_MSA_ONE_CLICK_DEMO_ENABLED: "false",
    };
    const origin = "https://id-preview--5df751a6-a78b-4e1d-8847-de6364a53f63.lovable.app";
    const req = (auth?: string, otherOrigin = origin) =>
      new Request(`${origin}/api/demo-call`, {
        method: "POST",
        headers: {
          origin: otherOrigin,
          "sec-fetch-site": "same-origin",
          ...(auth ? { Authorization: auth } : {}),
        },
      });
    expect((await authorizeSandboxRequest(hosted, req())).ok).toBe(false);
    expect((await authorizeSandboxRequest(hosted, req(`Bearer ${"c".repeat(32)}`))).ok).toBe(true);
    expect(
      (
        await authorizeSandboxRequest(
          hosted,
          req(`Bearer ${"c".repeat(32)}`, "https://evil.example"),
        )
      ).ok,
    ).toBe(false);
  });
});

describe("media token validation", () => {
  const jwt = `eyJhbGciOiJIUzI1NiJ9.${"a".repeat(600)}.sig_-x`;
  const tok = {
    server_url: "wss://lk.example.test",
    participant_token: jwt,
    room_name: "vab-vs-1",
    voice_session_id: "vs-1",
  };
  it("accepts a realistic JWT longer than 256 characters", () => {
    expect(jwt.length).toBeGreaterThan(256);
    expect(validateMediaToken(tok, "vs-1")).not.toBeNull();
  });
  it("rejects oversized, non-JWT, non-wss and wrong-scope tokens", () => {
    expect(
      validateMediaToken({ ...tok, participant_token: `a.${"b".repeat(4100)}.c` }, "vs-1"),
    ).toBeNull();
    expect(validateMediaToken({ ...tok, participant_token: "not a jwt" }, "vs-1")).toBeNull();
    expect(
      validateMediaToken({ ...tok, server_url: "https://lk.example.test" }, "vs-1"),
    ).toBeNull();
    expect(validateMediaToken({ ...tok, room_name: "vab-other" }, "vs-1")).toBeNull();
  });
});

describe("one-click call flow", () => {
  const started = {
    case_id: "DEMO-PC-VOICE-INTAKE-001",
    interaction_id: "int-1",
    voice_session_id: "vs-1",
    server_url: "wss://lk.example.test",
    participant_token: "a.b.c",
  };
  const mockFetch = (start: () => Response) => {
    const calls: { url: string; body: Record<string, unknown>; auth: string | null }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        calls.push({ url, body, auth: new Headers(init.headers).get("authorization") });
        if (body.action === "start") return start();
        if (body.action === "status")
          return new Response(
            JSON.stringify({ backend_connected: true, browser_softphone_enabled: true }),
            { status: 200 },
          );
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }),
    );
    return calls;
  };

  it("reports a media disconnect as one terminal event for after-call work", async () => {
    const calls = mockFetch(() => new Response(JSON.stringify(started), { status: 200 }));
    const { useOneClickCall } = await import("@/components/msa/use-one-click-call");
    const ended = vi.fn();
    const { result } = renderHook(() => useOneClickCall({ onSession: vi.fn(), onEnded: ended }));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(() => result.current.start());
    const room = lk.rooms[0] as unknown as { handlers: Record<string, () => void> };
    await act(async () => {
      room.handlers["d"]!();
    });
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(calls.filter((c) => c.body["action"] === "end")).toHaveLength(1);
    expect(calls.at(-1)?.body).toEqual({
      action: "end",
      voice_session_id: "vs-1",
      reason: "DISCONNECTED",
    });
    expect(ended).toHaveBeenCalledOnce();
  });

  it("transfers backend IDs to the observer, sends no operator code, and hang-up re-enables start", async () => {
    const calls = mockFetch(() => new Response(JSON.stringify(started), { status: 200 }));
    const onSession = vi.fn();
    const onEnded = vi.fn();
    const { useOneClickCall } = await import("@/components/msa/use-one-click-call");
    const { result } = renderHook(() => useOneClickCall({ onSession, onEnded }));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(() => result.current.start());
    expect(result.current.phase).toBe("live");
    expect(onSession).toHaveBeenCalledWith({
      case_id: started.case_id,
      interaction_id: "int-1",
      voice_session_id: "vs-1",
    });
    expect(lk.rooms).toHaveLength(1);
    expect(calls.every((c) => c.auth === null)).toBe(true);
    await act(() => result.current.hangUp());
    expect(result.current.phase).toBe("ready");
    expect(onEnded).toHaveBeenCalled();
    expect(
      calls.some((c) => c.body["action"] === "end" && c.body["voice_session_id"] === "vs-1"),
    ).toBe(true);
  });

  it("hands only this call's ephemeral guest token to its activity observer", async () => {
    const guestToken = "a".repeat(64);
    mockFetch(
      () =>
        new Response(
          JSON.stringify({
            ...started,
            guest_call_token: guestToken,
            guest_expires_at: Date.now() + 300_000,
          }),
          { status: 200 },
        ),
    );
    const onSession = vi.fn();
    const { useOneClickCall } = await import("@/components/msa/use-one-click-call");
    const { result } = renderHook(() => useOneClickCall({ onSession, onEnded: vi.fn() }));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(() => result.current.start());
    expect(onSession).toHaveBeenCalledWith(
      {
        case_id: started.case_id,
        interaction_id: started.interaction_id,
        voice_session_id: started.voice_session_id,
      },
      undefined,
      guestToken,
    );
    await act(() => result.current.hangUp());
  });

  it("authorizes the hosted demo once and reuses the code for the call lifecycle", async () => {
    const code = "c".repeat(32);
    const calls: { action: string; auth: string | null }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body)) as { action: string };
        const auth = new Headers(init.headers).get("authorization");
        calls.push({ action: body.action, auth });
        if (!auth)
          return new Response(JSON.stringify({ error: "demo_access_required" }), { status: 403 });
        if (body.action === "start") return new Response(JSON.stringify(started), { status: 200 });
        if (body.action === "status")
          return new Response(
            JSON.stringify({ backend_connected: true, browser_softphone_enabled: true }),
            { status: 200 },
          );
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }),
    );
    const onSession = vi.fn();
    const { useOneClickCall } = await import("@/components/msa/use-one-click-call");
    const { result } = renderHook(() => useOneClickCall({ onSession, onEnded: vi.fn() }));
    await waitFor(() => expect(result.current.phase).toBe("authorization_required"));
    await act(() => result.current.setAccessCode(code));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(() => result.current.start());
    expect(result.current.phase).toBe("live");
    expect(onSession).toHaveBeenCalledWith(
      {
        case_id: started.case_id,
        interaction_id: started.interaction_id,
        voice_session_id: started.voice_session_id,
      },
      code,
    );
    await act(() => result.current.hangUp());
    expect(calls.some((c) => c.action === "start" && c.auth === `Bearer ${code}`)).toBe(true);
    expect(calls.some((c) => c.action === "end" && c.auth === `Bearer ${code}`)).toBe(true);
  });

  it("a failed start releases state and allows retry", async () => {
    mockFetch(
      () => new Response(JSON.stringify({ error: "avery_or_backend_not_ready" }), { status: 503 }),
    );
    const { useOneClickCall } = await import("@/components/msa/use-one-click-call");
    const { result } = renderHook(() => useOneClickCall({ onSession: vi.fn(), onEnded: vi.fn() }));
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(() => result.current.start());
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/Avery/);
    await act(() => result.current.start());
    expect(result.current.phase).toBe("error");
  });

  it("does not offer a call until browser voice is available, then lets the user retry", async () => {
    let checks = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        if (body.action !== "status")
          return new Response(JSON.stringify({ error: "unexpected" }), { status: 500 });
        checks++;
        return new Response(
          JSON.stringify({
            backend_connected: true,
            browser_softphone_enabled: checks > 1,
          }),
          { status: 200 },
        );
      }),
    );
    const { OneClickCallControls } = await import("@/components/msa/one-click-call");
    render(<OneClickCallControls onSession={vi.fn()} onEnded={vi.fn()} />);
    const retry = await screen.findByRole("button", { name: /Retry backend connection/i });
    expect(screen.queryByRole("button", { name: /Start Demo Call/i })).toBeNull();
    expect(screen.getByText(/browser voice is not configured/i)).toBeInTheDocument();
    await act(async () => {
      retry.click();
    });
    expect(await screen.findByRole("button", { name: /Start Demo Call/i })).toBeInTheDocument();
  });

  it("shows a not-configured empty state when the gateway is disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: "demo_call_gateway_disabled" }), { status: 403 }),
      ),
    );
    const { OneClickCallControls } = await import("@/components/msa/one-click-call");
    render(<OneClickCallControls onSession={vi.fn()} onEnded={vi.fn()} />);
    expect(await screen.findByText("Live demo backend not configured")).toBeInTheDocument();
    expect(screen.queryByLabelText(/operator access code/i)).toBeNull();
  });
});

describe("guest read-only activity feed", () => {
  it("polls only its own call without a staff observer token or a second LiveKit room", async () => {
    const guestToken = "b".repeat(64);
    const mockFetch = vi.fn(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body)) as {
        action: string;
        voice_session_id: string;
      };
      expect(body.action).toBe("activity");
      expect(body.voice_session_id).toBe("vs-guest");
      expect(new Headers(init.headers).get("x-vab-guest-session")).toBe(guestToken);
      expect(new Headers(init.headers).has("authorization")).toBe(false);
      return new Response(
        JSON.stringify({
          synthetic: true,
          interaction_id: "interaction-guest",
          case_id: "DEMO-PC-VOICE-INTAKE-001",
          correlation_id: "corr-guest",
          scheduling_encounter_id: "SE-guest",
          next_cursor: "evt-1",
          events: [
            {
              event_id: "evt-1",
              event_type: "intent_captured",
              source: "conversation",
              occurred_at: "2026-11-11T06:00:00Z",
              synthetic: true,
              interaction_id: "interaction-guest",
              case_id: "DEMO-PC-VOICE-INTAKE-001",
              correlation_id: "corr-guest",
              payload: {},
            },
          ],
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", mockFetch);
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result, unmount } = renderHook(() => useLiveMonitor());
    act(() =>
      result.current.connectGuestActivity({
        caseId: "DEMO-PC-VOICE-INTAKE-001",
        interactionId: "interaction-guest",
        voiceSessionId: "vs-guest",
        guestToken,
      }),
    );
    await waitFor(() => expect(result.current.projection?.events).toHaveLength(1));
    expect(result.current.phase).toBe("connected");
    expect(mockFetch).toHaveBeenCalledWith("/api/demo-call", expect.any(Object));
    expect(lk.rooms).toHaveLength(0);
    unmount();
  });
});

describe("observer retry", () => {
  it("retries only 409 voice_room_not_ready, without an operator code", async () => {
    vi.useFakeTimers();
    let n = 0;
    const auths: (string | null)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init: RequestInit) => {
        auths.push(new Headers(init.headers).get("authorization"));
        n++;
        return n <= 2
          ? new Response(JSON.stringify({ error: "voice_room_not_ready" }), { status: 409 })
          : new Response(JSON.stringify({ error: "x" }), { status: 403 });
      }),
    );
    const { useLiveMonitor } = await import("@/components/msa/use-live-monitor");
    const { result } = renderHook(() => useLiveMonitor());
    let p!: Promise<void>;
    act(() => {
      p = result.current.connect({ caseId: "DEMO-1", voiceSessionId: "vs-1", retryNotReady: true });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000);
      await p;
    });
    expect(n).toBe(3);
    expect(auths.every((a) => a === null)).toBe(true);
    expect(result.current.phase).toBe("error");
    vi.useRealTimers();
  });
});
