import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useOneClickCall } from "@/components/msa/use-one-click-call";

const { disconnect, microphone } = vi.hoisted(() => ({
  disconnect: vi.fn(async () => {}),
  microphone: vi.fn(async () => {}),
}));
const captionHandlers = new Map<string, (...args: unknown[]) => unknown>();
vi.mock("livekit-client", () => ({
  Room: class {
    remoteParticipants = new Map([["worker", { kind: 4 }]]);
    localParticipant = {
      identity: "caller",
      audioTrackPublications: new Map([["mic", {}]]),
      setMicrophoneEnabled: microphone,
      getTrackPublication: () => undefined,
    };
    on(name: string, handler: (...args: unknown[]) => unknown) {
      captionHandlers.set(name, handler);
      return this;
    }
    registerRpcMethod(name: string, handler: (...args: unknown[]) => unknown) {
      captionHandlers.set(name, handler);
    }
    registerTextStreamHandler(name: string, handler: (...args: unknown[]) => unknown) {
      captionHandlers.set(name, handler);
    }
    async connect() {}
    async startAudio() {}
    disconnect = disconnect;
  },
  RoomEvent: {
    TranscriptionReceived: "caption",
    TrackSubscribed: "track",
    TrackUnsubscribed: "untrack",
    ActiveSpeakersChanged: "speakers",
    Disconnected: "disconnect",
  },
  Track: { Kind: { Audio: "audio" }, Source: { Microphone: "microphone" } },
  ParticipantKind: { AGENT: 4 },
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("guest browser call deadline", () => {
  it.each([false, true])(
    "renews only with backend approval, otherwise ends safely (renewal=%s)",
    async (renewal) => {
      const calls: { action: string; voice_session_id?: string }[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url, init) => {
          const body = JSON.parse(init.body);
          calls.push(body);
          return new Response(
            JSON.stringify(
              body.action === "status"
                ? { backend_connected: true, browser_softphone_enabled: true }
                : body.action === "start"
                  ? {
                      case_id: "DEMO-PC-VOICE-INTAKE-001",
                      interaction_id: "int-test",
                      voice_session_id: "vs-expiry",
                      server_url: "wss://example.test",
                      participant_token: "test",
                      guest_call_token: "a".repeat(64),
                      guest_expires_at: Date.now() + 300_000,
                    }
                  : body.action === "renew" && renewal
                    ? { ok: true, guest_expires_at: Date.now() + 300_000 }
                    : { ok: true },
            ),
            { status: 200 },
          );
        }),
      );
      const ended = vi.fn();
      const { result } = renderHook(() => useOneClickCall({ onSession: vi.fn(), onEnded: ended }));
      await waitFor(() => expect(result.current.phase).toBe("ready"));
      vi.useFakeTimers();
      await act(async () => {
        await result.current.start();
      });
      expect(result.current.phase).toBe("live");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(270_000);
      });
      if (renewal) {
        expect(calls.some((c) => c.action === "renew")).toBe(true);
        await act(async () => {
          await vi.advanceTimersByTimeAsync(60_000);
        });
        expect(result.current.phase).toBe("live");
        expect(calls.filter((c) => c.action === "end")).toHaveLength(0);
        await act(async () => {
          await result.current.hangUp();
        });
        expect(disconnect).toHaveBeenCalledOnce();
        return;
      }
      expect(result.current.notice).toContain("Reconnecting");
      expect(calls.filter((c) => c.action === "end")).toHaveLength(0);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(disconnect).toHaveBeenCalledOnce();
      expect(calls.filter((c) => c.action === "end")).toEqual([
        { action: "end", voice_session_id: "vs-expiry", reason: "TIME_LIMIT" },
      ]);
      expect(result.current.phase).toBe("ready");
      expect(result.current.notice).toContain("could not be renewed");
      expect(ended).toHaveBeenCalledOnce();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      expect(calls.filter((c) => c.action === "end")).toHaveLength(1);
    },
  );
});

it("automatically shows caller and agent speech and merges repeat deliveries", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (_url, init) =>
        new Response(
          JSON.stringify(
            JSON.parse(init.body).action === "status"
              ? { backend_connected: true, browser_softphone_enabled: true }
              : {
                  case_id: "case",
                  interaction_id: "turn",
                  voice_session_id: "session",
                  server_url: "wss://example.test",
                  participant_token: "test",
                },
          ),
        ),
    ),
  );
  const { result } = renderHook(() => useOneClickCall({ onSession: vi.fn(), onEnded: vi.fn() }));
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  await act(async () => {
    await result.current.start();
  });
  await act(async () => {
    const text = captionHandlers.get("lk.transcription")!;
    await text(
      {
        info: {
          id: "1",
          attributes: {
            "lk.segment_id": "first",
            "lk.transcribed_track_id": "mic",
            "lk.transcription_final": "true",
          },
        },
        readAll: async () => "Tuesday works",
      },
      { identity: "worker" },
    );
    captionHandlers.get("caption")!([{ id: "first", text: "Tuesday", final: false }], {
      identity: "caller",
    });
    await text(
      { info: { id: "second", attributes: {} }, readAll: async () => "Let me check" },
      { identity: "worker" },
    );
    await text(
      { info: { id: "third", attributes: {} }, readAll: async () => "Yes" },
      { identity: "caller" },
    );
    await text(
      { info: { id: "other", attributes: {} }, readAll: async () => "Other speaker" },
      { identity: "observer" },
    );
    const rpc = captionHandlers.get("vab.caller-caption")!;
    const start = {
      callerIdentity: "worker",
      payload: JSON.stringify({ kind: "start", session: "session" }),
    };
    await expect(rpc({ ...start, callerIdentity: "observer" })).rejects.toThrow();
    await expect(rpc(start)).resolves.toBe("ready");
    await text(
      { info: { id: "masked", attributes: {} }, readAll: async () => "Withheld" },
      { identity: "caller" },
    );
    await rpc({
      callerIdentity: "worker",
      payload: JSON.stringify({
        session: "session",
        kind: "final",
        seq: 1,
        text: "My demo details",
      }),
    });
  });
  expect(result.current.transcript.map((x) => [x.speaker, x.text])).toEqual([
    ["Veteran", "Tuesday works"],
    ["Avery", "Let me check"],
    ["Veteran", "Yes"],
    ["Veteran", "My demo details"],
  ]);
});
