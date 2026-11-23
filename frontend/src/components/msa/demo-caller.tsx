/* eslint-disable prettier/prettier -- Local sandbox work-in-progress; formatted at Codespace release gate. */
import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  Headphones,
  LockKeyhole,
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
} from "lucide-react";
import type { Room } from "livekit-client";
import { Button } from "@/components/ui/button";

type StartedCall = {
  synthetic: true;
  case_id: string;
  interaction_id: string;
  voice_session_id: string;
  room_name: string;
  server_url: string;
  participant_token: string;
};
type SessionRef = Pick<StartedCall, "case_id" | "interaction_id" | "voice_session_id">;

const messages: Record<string, string> = {
  forbidden: "Incorrect sandbox operator code.",
  demo_call_gateway_disabled:
    "The local call gateway is disabled. Configure both services for synthetic monitoring.",
  voice_gateway_not_ready: "The backend is reachable, but LiveKit voice transport is not ready.",
  avery_or_backend_not_ready: "Avery or IBM Orchestrate is not ready to start a real voice call.",
  unknown_backend_case_or_session: "The backend could not find the synthetic intake session.",
  backend_call_failed: "The backend call failed. Verify port 8080 and the Avery worker.",
};

function failureMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected call error.";
}

/** No patient selector, roster in the browser, or scripted audio. */
export function DemoCaller() {
  const [operatorCode, setOperatorCode] = useState("");
  const [stage, setStage] = useState(
    "Enter your private sandbox operator code and initiate a synthetic incoming call.",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [muted, setMuted] = useState(false);
  const [averyAudio, setAveryAudio] = useState(false);
  const [session, setSession] = useState<SessionRef | null>(null);
  const roomRef = useRef<Room | null>(null);
  const codeRef = useRef("");
  const mediaElements = useRef<Set<HTMLMediaElement>>(new Set());
  codeRef.current = operatorCode;

  useEffect(() => {
    const elements = mediaElements.current;
    return () => {
      for (const element of elements) element.remove();
      elements.clear();
      void roomRef.current?.disconnect();
      roomRef.current = null;
      codeRef.current = "";
    };
  }, []);

  async function gateway<T>(
    action: "status" | "start" | "connected" | "end",
    voiceSessionId?: string,
  ): Promise<T> {
    const response = await fetch("/api/demo-call", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${codeRef.current}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        action,
        ...(voiceSessionId ? { voice_session_id: voiceSessionId } : {}),
      }),
      cache: "no-store",
    });
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      const key =
        body && typeof body === "object" && "error" in body
          ? String((body as { error: unknown }).error)
          : "";
      throw new Error(messages[key] ?? "Unable to reach the synthetic call gateway.");
    }
    return body as T;
  }

  async function initiate() {
    if (operatorCode.length < 32 || busy || roomRef.current || session) return;
    setBusy(true);
    setError("");
    setStage("Creating a new, unidentified synthetic voice interaction…");
    let room: Room | null = null;
    try {
      const call = await gateway<StartedCall>("start");
      setSession({
        case_id: call.case_id,
        interaction_id: call.interaction_id,
        voice_session_id: call.voice_session_id,
      });
      const { Room, RoomEvent, Track } = await import("livekit-client");
      room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== Track.Kind.Audio) return;
        const audio = track.attach();
        audio.autoplay = true;
        audio.hidden = true;
        document.body.appendChild(audio);
        mediaElements.current.add(audio);
        setAveryAudio(true);
        setStage("Avery audio track received · speak naturally to Avery");
      });
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((element) => {
          element.remove();
          mediaElements.current.delete(element);
        });
        setAveryAudio(false);
      });
      room.on(RoomEvent.Disconnected, () => {
        setConnected(false);
        setAveryAudio(false);
        setStage("LiveKit media disconnected");
      });
      setStage("Joining LiveKit and publishing your browser microphone…");
      await room.connect(call.server_url, call.participant_token);
      await room.startAudio();
      await room.localParticipant.setMicrophoneEnabled(true);
      setConnected(true);
      setMuted(false);
      setStage("Your microphone is live · waiting for Avery's greeting");
      try {
        await gateway<{ ok: true }>("connected", call.voice_session_id);
      } catch (cause) {
        setError(
          `LiveKit connected, but VAB session event was not confirmed: ${failureMessage(cause)}`,
        );
      }
    } catch (cause) {
      if (room) await room.disconnect();
      roomRef.current = null;
      for (const element of mediaElements.current) element.remove();
      mediaElements.current.clear();
      setConnected(false);
      setAveryAudio(false);
      setSession(null);
      setStage("Call was not established");
      setError(failureMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function toggleMute() {
    const room = roomRef.current;
    if (!room || !connected) return;
    try {
      await room.localParticipant.setMicrophoneEnabled(muted);
      setMuted(!muted);
    } catch (cause) {
      setError(failureMessage(cause));
    }
  }

  async function hangUp() {
    const room = roomRef.current;
    roomRef.current = null;
    if (room) await room.disconnect();
    for (const element of mediaElements.current) element.remove();
    mediaElements.current.clear();
    setConnected(false);
    setAveryAudio(false);
    setMuted(false);
    setStage("Browser microphone disconnected");
    if (!session) return;
    try {
      await gateway<{ ok: true }>("end", session.voice_session_id);
      setStage("Synthetic call ended and acknowledged by VAB");
    } catch {
      setError("Browser disconnected. VAB did not acknowledge the canonical call end.");
    } finally {
      setSession(null);
    }
  }

  const observerUrl = session
    ? `/?case_id=${encodeURIComponent(session.case_id)}&voice_session_id=${encodeURIComponent(session.voice_session_id)}`
    : "/";

  return (
    <main className="min-h-screen bg-background">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-header px-4 py-4 text-header-foreground">
        <div>
          <p className="text-sm font-semibold">Veteran Access Bridge</p>
          <h1 className="text-xl font-semibold">Autonomous Scheduling Command Center</h1>
          <p className="text-xs text-canvas-muted">Primary Care · MCP-Powered</p>
        </div>
        <Button asChild variant="outline">
          <a href="/">Back to Command Center</a>
        </Button>
      </header>
      <div className="mx-auto max-w-3xl space-y-4 p-4 sm:p-6">
        <section
          className="space-y-4 rounded-xl border bg-surface p-5 shadow-sm"
          aria-label="Incoming call demo"
        >
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <PhoneCall size={20} /> Initiate incoming demo call
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Play the role of a Veteran caller. Avery will ask why you are calling, collect
              identifying information, and use the backend MCP tools to verify a matching synthetic
              record. No patient is preselected or revealed here.
            </p>
          </div>
          <div className="rounded-md border bg-secondary/30 p-3 text-sm" role="status">
            {stage}
          </div>
          {error && (
            <p
              className="rounded-md border border-destructive p-3 text-sm text-destructive"
              role="alert"
            >
              {error}
            </p>
          )}
          <label className="block space-y-1 text-sm" htmlFor="operator-code">
            <span className="flex items-center gap-2 font-medium">
              <LockKeyhole size={16} /> Local sandbox operator access code
            </span>
            <input
              id="operator-code"
              type="password"
              autoComplete="off"
              className="min-h-11 w-full rounded-md border bg-background px-3"
              value={operatorCode}
              onChange={(event) => setOperatorCode(event.target.value)}
              disabled={connected}
            />
          </label>
          <Button
            size="lg"
            className="min-h-12 w-full gap-2"
            disabled={busy || !!session || operatorCode.length < 32}
            onClick={() => void initiate()}
          >
            <PhoneCall size={19} /> {busy ? "Connecting…" : "Initiate Demo Call"}
          </Button>
          <div className="space-y-1 text-sm">
            <p className="flex items-center gap-2">
              {connected ? <CheckCircle2 size={17} /> : <MicOff size={17} />}
              Microphone:{" "}
              {connected ? (muted ? "Muted" : "Publishing to LiveKit") : "Not connected"}
            </p>
            <p className="flex items-center gap-2">
              <Headphones size={17} />
              Avery audio: {averyAudio ? "Remote track received" : "Not received yet"}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" disabled={!connected} onClick={() => void toggleMute()}>
              {muted ? <MicOff size={16} /> : <Mic size={16} />} {muted ? "Unmute" : "Mute"}
            </Button>
            <Button variant="destructive" disabled={!roomRef.current} onClick={() => void hangUp()}>
              <PhoneOff size={16} /> Hang up
            </Button>
          </div>
          {session && (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <strong>Backend-generated, unselected intake session</strong>
              <dl className="grid gap-1 break-all text-xs">
                <dt className="font-semibold">Case ID</dt>
                <dd>{session.case_id}</dd>
                <dt className="font-semibold">Voice session ID</dt>
                <dd>{session.voice_session_id}</dd>
              </dl>
              <a
                className="inline-flex min-h-11 items-center rounded-md border px-3 font-semibold underline"
                href={observerUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Observe this call in Command Center
              </a>
              <p className="text-xs text-muted-foreground">
                Connect the read-only observer using the same sandbox operator code. The Command
                Center must not pretend to have a transcript or booking receipt.
              </p>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Synthetic microphone/WebRTC demonstration · No PSTN call · No real patient data · No
            production VA booking.
          </p>
        </section>
      </div>
    </main>
  );
}
