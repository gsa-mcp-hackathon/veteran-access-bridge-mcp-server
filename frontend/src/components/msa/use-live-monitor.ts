import { useCallback, useEffect, useRef, useState } from "react";
import type { RemoteAudioTrack, Room } from "livekit-client";
import {
  applyEventsPage,
  classifyParticipant,
  emptyProjection,
  validateToken,
  type MonitorProjection,
} from "@/lib/live-monitor";

export type MonitorPhase =
  "idle" | "authorizing" | "connecting" | "connected" | "reconnecting" | "disconnected" | "error";

export type LiveMonitor = ReturnType<typeof useLiveMonitor>;

const POLL_MS = 2500;
/** Bounded wait for Avery dispatch after the caller joins (409 only). */
export const NOT_READY_RETRY_MS = 3000;
export const NOT_READY_MAX_ATTEMPTS = 20;

class NotReadyError extends Error {}

async function gateway(code: string, body: Record<string, string | undefined>) {
  // Empty code = private one-click path; the server gate decides, never the browser.
  const res = await fetch("/api/msa-monitor", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(code ? { Authorization: `Bearer ${code}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // A 409 here is not a credential error. The Veteran must establish the
    // existing LiveKit room and Avery dispatch before the observer can join.
    if (res.status === 409 || res.status === 503) {
      let code: unknown;
      try {
        const body = (await res.json()) as { error?: unknown } | null;
        code = body?.error;
      } catch {
        // Never trust arbitrary gateway response content.
      }
      if (res.status === 409 && code === "voice_room_not_ready")
        throw new NotReadyError(
          "Start the synthetic Veteran call and Avery first, then reconnect the observer.",
        );
      if (res.status === 503 && code === "voice_room_readiness_unavailable")
        throw new Error("LiveKit readiness unavailable; observer remains disconnected.");
    }
    throw new Error(
      res.status === 403 ? "Monitor gateway refused access" : "Monitor gateway unavailable",
    );
  }
  return res.json() as Promise<unknown>;
}

/**
 * Authoritative observer. The operator code lives only in this hook's ref and
 * is cleared on disconnect. Never persisted.
 */
export function useLiveMonitor() {
  const [phase, setPhase] = useState<MonitorPhase>("idle");
  const [error, setError] = useState("");
  const [projection, setProjection] = useState<MonitorProjection | null>(null);
  const [agentTrack, setAgentTrack] = useState<RemoteAudioTrack | null>(null);
  const [callerTrack, setCallerTrack] = useState<RemoteAudioTrack | null>(null);
  const [monitoring, setMonitoringState] = useState(false);
  const room = useRef<Room | null>(null);
  const code = useRef("");
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Attached playback elements keyed by subscribed track; at most one per track. */
  const audioEls = useRef(new Map<RemoteAudioTrack, HTMLMediaElement>());

  const detachOne = (track: RemoteAudioTrack) => {
    const el = audioEls.current.get(track);
    if (!el) return;
    audioEls.current.delete(track);
    try {
      track.detach(el);
    } catch {
      /* track already stopped */
    }
    el.remove();
  };
  const detachAudio = () => {
    [...audioEls.current.keys()].forEach(detachOne);
  };

  const dispose = useCallback(() => {
    generation.current += 1;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    detachAudio();
    void room.current?.disconnect();
    room.current = null;
    code.current = "";
    setAgentTrack(null);
    setCallerTrack(null);
    setMonitoringState(false);
  }, []);

  useEffect(() => dispose, [dispose]);

  const disconnect = useCallback(() => {
    dispose();
    setProjection(null);
    setError("");
    setPhase("idle");
  }, [dispose]);

  const stop = useCallback(() => {
    dispose();
    setError("");
    setPhase("disconnected");
    // Preserve verified observations for after-call review; stop expired-token polls.
  }, [dispose]);

  const connect = useCallback(
    async (input: {
      accessCode?: string;
      caseId: string;
      voiceSessionId: string;
      /** Retry only 409 voice_room_not_ready for a bounded interval. */
      retryNotReady?: boolean;
    }) => {
      dispose();
      const gen = generation.current;
      code.current = input.accessCode ?? "";
      setError("");
      setProjection(null);
      setPhase("authorizing");
      const fail = (message: string) => {
        if (gen !== generation.current) return;
        dispose();
        setError(message);
        setPhase("error");
      };
      try {
        let raw: unknown;
        for (let attempt = 1; ; attempt++) {
          try {
            raw = await gateway(code.current, {
              action: "token",
              case_id: input.caseId,
              voice_session_id: input.voiceSessionId,
            });
            break;
          } catch (e) {
            if (
              !(e instanceof NotReadyError) ||
              !input.retryNotReady ||
              attempt >= NOT_READY_MAX_ATTEMPTS
            )
              throw e;
            if (gen !== generation.current) return;
            setError("Waiting for Avery to join the call…");
            await new Promise((r) => setTimeout(r, NOT_READY_RETRY_MS));
            if (gen !== generation.current) return;
          }
        }
        setError("");
        const token = validateToken(raw, {
          case_id: input.caseId,
          voice_session_id: input.voiceSessionId,
        });
        if (gen !== generation.current) return;
        if (!token) return fail("Monitor token failed contract validation");
        let state = emptyProjection(token.interaction_id, token.case_id);
        setProjection(state);

        const poll = async () => {
          if (gen !== generation.current) return;
          try {
            const page = await gateway(code.current, {
              action: "events",
              case_id: token.case_id,
              interaction_id: token.interaction_id,
              cursor: state.cursor ?? undefined,
            });
            if (gen !== generation.current) return;
            const result = applyEventsPage(state, page);
            if (!result.ok) return fail(`Event feed rejected: ${result.reason}`);
            state = result.state;
            setProjection(state);
          } catch {
            if (gen !== generation.current) return;
            setError("Event feed temporarily unavailable; retrying");
          }
          if (gen === generation.current) timer.current = setTimeout(poll, POLL_MS);
        };
        void poll();

        setPhase("connecting");
        const { Room, RoomEvent, Track, ParticipantKind } = await import("livekit-client");
        if (gen !== generation.current) return;
        const r = new Room({ adaptiveStream: false, dynacast: false });
        room.current = r;
        r.on(RoomEvent.Connected, () => gen === generation.current && setPhase("connected"))
          .on(RoomEvent.Reconnecting, () => gen === generation.current && setPhase("reconnecting"))
          .on(RoomEvent.Reconnected, () => gen === generation.current && setPhase("connected"))
          .on(RoomEvent.Disconnected, () => {
            if (gen !== generation.current) return;
            setAgentTrack(null);
            setCallerTrack(null);
            setPhase("disconnected");
          })
          .on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
            if (gen !== generation.current || track.kind !== Track.Kind.Audio) return;
            const role = classifyParticipant({
              isAgent: participant.kind === ParticipantKind.AGENT,
              metadata: participant.metadata,
            });
            if (role === "agent") setAgentTrack(track as RemoteAudioTrack);
            if (role === "caller") setCallerTrack(track as RemoteAudioTrack);
          })
          .on(RoomEvent.TrackUnsubscribed, (track) => {
            if (gen !== generation.current) return;
            track.detach().forEach((el) => el.remove());
            setAgentTrack((t) => (t === track ? null : t));
            setCallerTrack((t) => (t === track ? null : t));
          })
          .on(RoomEvent.ParticipantDisconnected, (participant) => {
            if (gen !== generation.current) return;
            participant.audioTrackPublications.forEach((pub) => {
              setAgentTrack((t) => (t && t === pub.track ? null : t));
              setCallerTrack((t) => (t && t === pub.track ? null : t));
            });
          });
        await r.connect(token.server_url, token.participant_token, { autoSubscribe: true });
      } catch (e) {
        fail(e instanceof Error ? e.message : "Monitor connection failed");
      }
    },
    [dispose],
  );

  /**
   * Guest CALLER read-only activity (not staff monitoring). A 64-hex ephemeral
   * guest token authorizes only this voice session at the same-origin BFF.
   * This path NEVER requests an MSA monitor token or joins a LiveKit room.
   */
  const connectGuestActivity = useCallback(
    (input: {
      caseId: string;
      interactionId: string;
      voiceSessionId: string;
      guestToken: string;
    }) => {
      dispose();
      const gen = generation.current;
      if (!/^[0-9a-f]{64}$/.test(input.guestToken)) {
        setPhase("error");
        setError("Call activity authorization unavailable");
        return;
      }
      let state = emptyProjection(input.interactionId, input.caseId);
      setProjection(state);
      setPhase("authorizing");
      setError("");
      const poll = async () => {
        if (gen !== generation.current) return;
        try {
          const response = await fetch("/api/demo-call", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-VAB-Guest-Call": "1",
              "X-VAB-Guest-Session": input.guestToken,
            },
            body: JSON.stringify({
              action: "activity",
              voice_session_id: input.voiceSessionId,
              ...(state.cursor ? { cursor: state.cursor } : {}),
            }),
            signal: AbortSignal.timeout(10000),
            cache: "no-store",
          });
          if (gen !== generation.current) return;
          if (response.status === 403) {
            setError("Call activity is not authorized or its session has expired");
            setPhase("error");
            return;
          }
          if (!response.ok) throw new Error("activity_unavailable");
          const result = applyEventsPage(state, await response.json());
          if (gen !== generation.current) return;
          if (!result.ok) {
            setError(`Caller event scope rejected: ${result.reason}`);
            setPhase("error");
            return;
          }
          state = result.state;
          setProjection(state);
          setPhase("connected");
          setError("");
        } catch {
          if (gen !== generation.current) return;
          setPhase("reconnecting");
          setError("Call activity temporarily unavailable; retrying read-only feed");
        }
        if (gen === generation.current) timer.current = setTimeout(poll, POLL_MS);
      };
      void poll();
    },
    [dispose],
  );

  /**
   * Playback reconciliation: while monitoring is on (only after an explicit
   * gesture), attach each currently subscribed recognized track exactly once,
   * including tracks that arrive after the Monitor click; detach replaced or
   * unsubscribed tracks; detach everything when monitoring turns off.
   */
  useEffect(() => {
    const wanted = new Set<RemoteAudioTrack>();
    if (monitoring) {
      if (agentTrack) wanted.add(agentTrack);
      if (callerTrack) wanted.add(callerTrack);
    }
    for (const t of [...audioEls.current.keys()]) if (!wanted.has(t)) detachOne(t);
    for (const t of wanted) {
      if (audioEls.current.has(t)) continue;
      const el = t.attach();
      el.hidden = true;
      document.body.appendChild(el);
      audioEls.current.set(t, el);
    }
  }, [monitoring, agentTrack, callerTrack]);

  /** Local playback of subscribed audio only; requires a user gesture. */
  const setMonitoring = useCallback(async (on: boolean) => {
    if (!on || !room.current) {
      setMonitoringState(false);
      return;
    }
    const gen = generation.current;
    try {
      await room.current.startAudio();
    } catch {
      if (gen !== generation.current) return;
      setMonitoringState(false);
      setError("Browser blocked monitor audio; monitoring remains off");
      return;
    }
    if (gen !== generation.current || !room.current) return;
    setMonitoringState(true);
  }, []);

  return {
    active: phase !== "idle",
    phase,
    error,
    projection,
    agentTrack,
    callerTrack,
    monitoring,
    connect,
    connectGuestActivity,
    disconnect,
    stop,
    setMonitoring,
  };
}
