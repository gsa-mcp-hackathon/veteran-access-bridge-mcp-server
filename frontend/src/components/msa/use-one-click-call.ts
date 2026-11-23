import { usePrivateIdentity } from "./use-private-identity";
import { useCallback, useEffect, useRef, useState } from "react";
import type { LocalAudioTrack, RemoteAudioTrack, Room } from "livekit-client";
import { classifyParticipant } from "@/lib/live-monitor";
import { projectAfterCall, type AfterCall } from "@/lib/after-call";
import { createLatencyProbe, observeDecodedAudio } from "@/lib/latency-probe";

export type CallPhase =
  | "checking"
  | "unconfigured"
  | "authorization_required"
  | "unavailable"
  | "ready"
  | "starting"
  | "joining"
  | "live"
  | "ending"
  | "error";

export type CallSession = {
  case_id: string;
  interaction_id: string;
  voice_session_id: string;
};

/** Ephemeral LiveKit text-stream captions, not canonical backend transcripts. */
export type LiveTranscriptLine = {
  id: string;
  speaker: "Veteran" | "Avery";
  text: string;
  final: boolean;
  receivedAt: number;
  source?: "typed";
};

const ID = /^[A-Za-z0-9_-]{1,64}$/;

const MESSAGES: Record<string, string> = {
  forbidden: "Demo access code not accepted or this request was blocked.",
  demo_access_required: "Enter your private demo access code once to connect to Avery.",
  demo_call_gateway_disabled: "Live demo backend not configured for this environment.",
  voice_gateway_not_ready: "Backend reachable, but LiveKit voice transport is not ready.",
  avery_or_backend_not_ready: "Avery or the backend is not ready to take a call.",
  unknown_backend_case_or_session: "The backend could not find the synthetic intake case.",
  backend_call_failed:
    "The scheduling service could not complete the request. Check the connected backend.",
};

class GatewayError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

/** No service credentials in the browser. An optional demo operator code is memory-only. */
async function demoGateway<T>(
  body: Record<string, string>,
  accessCode = "",
  guestToken = "",
): Promise<T> {
  const res = await fetch("/api/demo-call", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VAB-Guest-Call": "1",
      ...(accessCode ? { Authorization: `Bearer ${accessCode}` } : {}),
      ...(guestToken ? { "X-VAB-Guest-Session": guestToken } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    const code =
      data && typeof data === "object" && "error" in data
        ? String((data as { error: unknown }).error)
        : "";
    throw new GatewayError(code, MESSAGES[code] ?? "Unable to reach the synthetic call gateway.");
  }
  return data as T;
}

/**
 * Real browser-microphone caller for the private one-click demo. Joins the
 * backend-created LiveKit room once, hands backend IDs to the observer via
 * onSession, and always releases state on failure or hang-up.
 */
export function useOneClickCall(opts: {
  onSession: (s: CallSession, accessCode?: string, guestToken?: string) => void;
  onEnded: () => void;
}) {
  const [agentPreparing, setAgentPreparing] = useState(false);
  const [phase, setPhase] = useState<CallPhase>("checking");
  const [statusCheck, setStatusCheck] = useState(0);
  const [accessCode, setAccessCode] = useState("");
  const accessRef = useRef("");
  const guestTokenRef = useRef("");
  accessRef.current = accessCode;
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [afterCall, setAfterCall] = useState<AfterCall | null>(null);
  const finishRef = useRef<(expired?: boolean, disconnected?: boolean) => Promise<void>>(
    async () => {},
  );
  const lastEnd = useRef<{ voice_session_id: string; reason: string } | null>(null);
  const [guestDeadline, setGuestDeadline] = useState<number | null>(null);
  const [muted, setMuted] = useState(false);
  const [averyAudio, setAveryAudio] = useState(false);
  const [agentTrack, setAgentTrack] = useState<RemoteAudioTrack | null>(null);
  const [microphoneTrack, setMicrophoneTrack] = useState<LocalAudioTrack | null>(null);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [veteranSpeaking, setVeteranSpeaking] = useState(false);
  const [transcript, setTranscript] = useState<LiveTranscriptLine[]>([]);
  const room = useRef<Room | null>(null);
  const privateIdentity = usePrivateIdentity(room, phase, setMuted);
  const session = useRef<CallSession | null>(null);
  const elements = useRef(new Set<HTMLMediaElement>());
  const latency = useRef(createLatencyProbe((sample) => console.info("VAB latency", sample)));
  const audioProbe = useRef<(() => void) | null>(null);
  const probeEnabled = import.meta.env["VITE_ENABLE_LATENCY_PROBE"] === "true";
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const release = useCallback(async () => {
    setGuestDeadline(null);
    audioProbe.current?.();
    audioProbe.current = null;
    latency.current.reset();
    const r = room.current;
    room.current = null;
    elements.current.forEach((el) => el.remove());
    elements.current.clear();
    setAveryAudio(false);
    setAgentTrack(null);
    setMicrophoneTrack(null);
    setAgentSpeaking(false);
    setVeteranSpeaking(false);
    setMuted(false);
    if (r) await r.disconnect().catch(() => undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPhase("checking");
    setError("");
    demoGateway<{ backend_connected?: boolean; browser_softphone_enabled?: boolean }>(
      { action: "status" },
      accessRef.current,
    )
      .then((status) => {
        if (cancelled) return;
        if (status.backend_connected !== true || status.browser_softphone_enabled !== true) {
          setPhase("unavailable");
          setError(
            status.backend_connected === true
              ? "VAB is reachable, but browser voice is not configured. Check LiveKit and Avery."
              : "VAB did not confirm a backend connection.",
          );
          return;
        }
        setPhase("ready");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const code = e instanceof GatewayError ? e.code : "";
        setPhase(
          code === "demo_call_gateway_disabled"
            ? "unconfigured"
            : code === "demo_access_required" || code === "forbidden"
              ? "authorization_required"
              : "unavailable",
        );
        if (code !== "demo_call_gateway_disabled") {
          setError(e instanceof Error ? e.message : "The demo backend is unavailable.");
        }
      });
    return () => {
      cancelled = true;
      void release();
    };
  }, [release, statusCheck, accessCode]);

  const retryStatus = useCallback(() => setStatusCheck((n) => n + 1), []);

  const start = useCallback(async () => {
    if (room.current || session.current) return;
    setError("");
    setTranscript([]);
    setNotice("");
    setAgentPreparing(false);
    setPhase("starting");
    setAfterCall(null);
    lastEnd.current = null;
    try {
      const call = await demoGateway<
        CallSession & {
          server_url: string;
          participant_token: string;
          guest_call_token?: string;
          guest_expires_at?: number;
        }
      >({ action: "start" }, accessRef.current);
      if (
        !ID.test(call.case_id) ||
        !ID.test(call.interaction_id) ||
        !ID.test(call.voice_session_id) ||
        typeof call.server_url !== "string" ||
        typeof call.participant_token !== "string"
      )
        throw new Error("Call gateway returned an invalid session.");
      if (call.guest_call_token !== undefined && !/^[0-9a-f]{64}$/.test(call.guest_call_token))
        throw new Error("Call gateway returned an invalid session credential.");
      guestTokenRef.current = call.guest_call_token ?? "";
      if (
        call.guest_call_token &&
        (!Number.isSafeInteger(call.guest_expires_at) || call.guest_expires_at! <= Date.now())
      )
        throw new Error("The demo session has expired. Please start a new call.");
      const ids: CallSession = {
        case_id: call.case_id,
        interaction_id: call.interaction_id,
        voice_session_id: call.voice_session_id,
      };
      session.current = ids;
      setPhase("joining");
      const { Room, RoomEvent, Track, ParticipantKind } = await import("livekit-client");
      const r = new Room({ adaptiveStream: true, dynacast: true });
      room.current = r;

      function captionSpeaker(
        identity: string,
        trackId?: string,
      ): LiveTranscriptLine["speaker"] | null {
        if (identity === r.localParticipant.identity) return "Veteran";
        const remote = r.remoteParticipants.get(identity);
        if (
          !remote ||
          classifyParticipant({
            isAgent: remote.kind === ParticipantKind.AGENT,
            metadata: remote.metadata,
          }) !== "agent"
        )
          return null;
        // The agent can publish transcriptions for the caller's microphone.
        if (trackId && r.localParticipant.audioTrackPublications?.has(trackId)) return "Veteran";
        return "Avery";
      }
      function receiveCaption(line: LiveTranscriptLine) {
        if (room.current !== r || !line.text || line.text.length > 1800) return;
        setTranscript((current) => {
          const index = current.findIndex(
            (old) => old.speaker === line.speaker && old.id === line.id,
          );
          if (index < 0) return [...current, line];
          if (current[index]?.final && !line.final) return current;
          return current.map((old, i) =>
            i === index ? { ...line, receivedAt: old.receivedAt } : old,
          );
        });
      }
      let privateCallerCaptions = false;
      r.registerRpcMethod?.("vab.caller-caption", async (data) => {
        const agent = r.remoteParticipants.get(data.callerIdentity);
        if (
          room.current !== r ||
          agent?.kind !== ParticipantKind.AGENT ||
          data.payload.length > 6000
        )
          throw new Error("Caption unavailable");
        const message = JSON.parse(data.payload);
        if (message.session !== ids.voice_session_id) throw new Error("Wrong call");
        if (message.kind === "start") {
          privateCallerCaptions = true;
          return "ready";
        }
        if (
          !privateCallerCaptions ||
          message.kind !== "final" ||
          !Number.isSafeInteger(message.seq) ||
          typeof message.text !== "string" ||
          message.text.length > 1800
        )
          throw new Error("Invalid caption");
        receiveCaption({
          id: "caller-" + message.seq,
          speaker: "Veteran",
          text: message.text,
          final: true,
          receivedAt: Date.now(),
        });
        return "received";
      });
      r.on(RoomEvent.TranscriptionReceived, (segments, participant, publication) => {
        if (!participant) return;
        const speaker = captionSpeaker(participant.identity, publication?.trackSid);
        if (!speaker || (speaker === "Veteran" && privateCallerCaptions)) return;
        for (const segment of segments) {
          receiveCaption({
            id: segment.id,
            speaker,
            text: segment.text.trim(),
            final: segment.final,
            receivedAt: Date.now(),
          });
        }
      });
      // AgentSession publishes both Veteran STT and Avery speech text to this
      // LiveKit stream. Never render text from an unknown room participant.
      if (typeof r.registerTextStreamHandler === "function") {
        if (probeEnabled)
          r.registerTextStreamHandler("vab.latency.ready", async (reader, info) => {
            const remote = r.remoteParticipants.get(info.identity);
            if (
              !remote ||
              classifyParticipant({
                isAgent: remote.kind === ParticipantKind.AGENT,
                metadata: remote.metadata,
              }) !== "agent"
            )
              return;
            try {
              const raw = await reader.readAll();
              if (raw.length > 128 || room.current !== r) return;
              latency.current.ready(JSON.parse(raw).trace_id, performance.now());
            } catch {
              /* Diagnostics cannot interrupt the call. */
            }
          });
        r.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
          try {
            const attrs = reader.info.attributes;
            const speaker = captionSpeaker(
              participantInfo.identity,
              attrs?.["lk.transcribed_track_id"],
            );
            if (!speaker || (speaker === "Veteran" && privateCallerCaptions)) return;
            const text = (await reader.readAll()).trim();
            receiveCaption({
              id: attrs?.["lk.segment_id"] ?? reader.info.id,
              speaker,
              text,
              final: attrs?.["lk.transcription_final"] === "true",
              receivedAt: Date.now(),
            });
          } catch {
            // Interrupted text streams are not treated as spoken words.
          }
        });
      }

      r.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (track.kind !== Track.Kind.Audio) return;
        const role = classifyParticipant({
          isAgent: participant.kind === ParticipantKind.AGENT,
          metadata: participant.metadata,
        });
        if (role !== "agent") return;
        if (probeEnabled) {
          audioProbe.current?.();
          try {
            audioProbe.current = observeDecodedAudio(track.mediaStreamTrack, latency.current);
          } catch {
            latency.current.reset();
            audioProbe.current = null;
          }
        }
        setAgentTrack(track as RemoteAudioTrack);
        const el = track.attach();
        el.hidden = true;
        document.body.appendChild(el);
        elements.current.add(el);
        setAveryAudio(true);
      })
        .on(RoomEvent.TrackUnsubscribed, (track) => {
          if (track.kind === Track.Kind.Audio) {
            audioProbe.current?.();
            audioProbe.current = null;
          }
          track.detach().forEach((el) => {
            el.remove();
            elements.current.delete(el);
          });
          setAgentTrack((current) => (current === track ? null : current));
          setAgentSpeaking(false);
          setAveryAudio(false);
        })
        .on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
          if (participant.kind === ParticipantKind.AGENT && "lk.agent.state" in changed)
            setAgentPreparing(changed["lk.agent.state"] === "thinking");
        })
        .on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          setVeteranSpeaking(speakers.some((p) => p.identity === r.localParticipant.identity));
          const agentIsSpeaking = speakers.some((p) => {
            const role = classifyParticipant({
              isAgent: p.kind === ParticipantKind.AGENT,
              metadata: p.metadata,
            });
            return role === "agent";
          });
          setAgentSpeaking(agentIsSpeaking);
        })
        .on(RoomEvent.Disconnected, () => {
          if (room.current !== r) return;
          void finishRef.current(false, true);
        });
      await r.connect(call.server_url, call.participant_token);
      if (call.guest_call_token && call.guest_expires_at! <= Date.now())
        throw new Error("The demo session expired while connecting. Please start a new call.");
      await r.startAudio();
      await r.localParticipant.setMicrophoneEnabled(true);
      const publication = r.localParticipant.getTrackPublication(Track.Source.Microphone);
      setMicrophoneTrack((publication?.track as LocalAudioTrack | undefined) ?? null);
      setPhase("live");
      setGuestDeadline(call.guest_call_token ? call.guest_expires_at! : null);
      if (accessRef.current) optsRef.current.onSession(ids, accessRef.current);
      else if (guestTokenRef.current)
        optsRef.current.onSession(ids, undefined, guestTokenRef.current);
      else optsRef.current.onSession(ids);
      demoGateway(
        { action: "connected", voice_session_id: ids.voice_session_id },
        accessRef.current,
        guestTokenRef.current,
      ).catch(() => setError("Call connected, but the backend did not confirm the session event."));
    } catch (e) {
      const ended = session.current;
      await release();
      session.current = null;
      if (ended)
        void demoGateway(
          { action: "end", voice_session_id: ended.voice_session_id },
          accessRef.current,
          guestTokenRef.current,
        ).catch(() => undefined);
      guestTokenRef.current = "";
      setError(e instanceof Error ? e.message : "Call was not established.");
      setPhase(
        e instanceof GatewayError && e.code === "demo_call_gateway_disabled"
          ? "unconfigured"
          : e instanceof GatewayError &&
              (e.code === "demo_access_required" || e.code === "forbidden")
            ? "authorization_required"
            : "error",
      );
      optsRef.current.onEnded();
    }
  }, [release, probeEnabled]);

  const retryAfterCall = useCallback(async () => {
    const ended = lastEnd.current;
    if (!ended) return;
    setAfterCall({ status: "PENDING", persisted: false });
    try {
      const result = await demoGateway<{ after_call?: unknown }>(
        { action: "end", ...ended },
        accessRef.current,
        guestTokenRef.current,
      );
      if (lastEnd.current !== ended) return;
      setAfterCall(
        projectAfterCall(result.after_call) ?? { status: "UNAVAILABLE", persisted: false },
      );
    } catch {
      if (lastEnd.current !== ended) return;
      setAfterCall({ status: "PENDING", persisted: false });
      setError(
        "Call ended; after-call work is not confirmed. Retry shortly or ask staff to review.",
      );
    }
  }, []);

  const hangUp = useCallback(
    async (expired = false, disconnected = false) => {
      const ended = session.current;
      session.current = null;
      setPhase("ending");
      await release();
      optsRef.current.onEnded();
      if (ended) {
        lastEnd.current = {
          voice_session_id: ended.voice_session_id,
          reason: expired ? "TIME_LIMIT" : disconnected ? "DISCONNECTED" : "CALLER_ENDED",
        };
        await retryAfterCall();
      }
      setNotice(
        expired ? "The secure call connection could not be renewed. Please start a new call." : "",
      );
      setPhase("ready");
    },
    [release, retryAfterCall],
  );
  finishRef.current = hangUp;

  useEffect(() => {
    if (guestDeadline === null) return;
    let cancelled = false;
    let renewing = false;
    const renew = async () => {
      const current = session.current;
      if (!current || renewing || cancelled) return;
      renewing = true;
      try {
        const result = await demoGateway<{ guest_expires_at: number }>(
          { action: "renew", voice_session_id: current.voice_session_id },
          accessRef.current,
          guestTokenRef.current,
        );
        if (
          !cancelled &&
          session.current === current &&
          Number.isSafeInteger(result.guest_expires_at) &&
          result.guest_expires_at > Date.now()
        ) {
          setGuestDeadline(result.guest_expires_at);
          setNotice("");
        }
      } catch {
        // Transient failures can retry within the existing short lease.
      } finally {
        renewing = false;
      }
    };
    const check = () => {
      if (Date.now() >= guestDeadline) void hangUp(true);
      else if (Date.now() >= guestDeadline - 30_000)
        setNotice("Reconnecting your secure call session…");
    };
    const renewal = window.setInterval(() => void renew(), 60_000);
    const warning = window.setTimeout(check, Math.max(0, guestDeadline - Date.now() - 30_000));
    const expiry = window.setTimeout(check, Math.max(0, guestDeadline - Date.now()));
    document.addEventListener("visibilitychange", check);
    check();
    return () => {
      cancelled = true;
      window.clearInterval(renewal);
      window.clearTimeout(warning);
      window.clearTimeout(expiry);
      document.removeEventListener("visibilitychange", check);
    };
  }, [guestDeadline, hangUp]);

  const sendTypedReply = useCallback(async (text: string) => {
    const r = room.current;
    const clean = text.trim();
    if (!r || !session.current || !clean || clean.length > 512) return false;
    try {
      await r.localParticipant.sendText(clean, { topic: "vab.caller-reply" });
      setTranscript((lines) => [
        ...lines,
        {
          id: crypto.randomUUID(),
          speaker: "Veteran",
          text: clean,
          final: true,
          receivedAt: Date.now(),
          source: "typed",
        },
      ]);
      return true;
    } catch {
      setError("Your typed reply was not sent. Please try again.");
      return false;
    }
  }, []);

  const toggleMute = useCallback(async () => {
    if (privateIdentity.required) return;
    const r = room.current;
    if (!r) return;
    try {
      await r.localParticipant.setMicrophoneEnabled(muted);
      setMuted(!muted);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Microphone change failed.");
    }
  }, [muted, privateIdentity.required]);

  return {
    agentPreparing: phase === "live" && agentPreparing,
    privateIdentity,
    phase,
    error,
    notice,
    afterCall,
    retryAfterCall,
    muted,
    averyAudio,
    agentTrack,
    microphoneTrack,
    agentSpeaking,
    veteranSpeaking,
    transcript,
    start,
    hangUp,
    toggleMute,
    sendTypedReply,
    retryStatus,
    setAccessCode,
  };
}
