/* eslint-disable prettier/prettier -- Screen A feature branch: run Prettier at integration/release gate. */
import { PrivateIdentityField } from "./private-identity-field";
import { lazy, Suspense, useEffect, useState } from "react";
import { ClientOnly } from "@tanstack/react-router";
import type { AgentState } from "@livekit/components-react";
import type { LocalAudioTrack } from "livekit-client";
import {
  AudioLines,
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
  RefreshCw,
  ChevronDown,
  ClipboardList,
  Headset,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CallSession, LiveTranscriptLine } from "./use-one-click-call";
import { useOneClickCall } from "./use-one-click-call";
import type { AfterCall } from "@/lib/after-call";

const ScreenAOrb = lazy(() => import("./screen-a-orb"));

function MicWave({ track, muted }: { track: LocalAudioTrack | null; muted: boolean }) {
  const [bars, setBars] = useState<number[]>(Array(12).fill(2));
  useEffect(() => {
    if (!track || muted) return;
    let frame = 0;
    let stopped = false;
    let cleanup: (() => Promise<void>) | undefined;
    void import("livekit-client").then(({ createAudioAnalyser }) => {
      if (stopped) return;
      const result = createAudioAnalyser(track, { fftSize: 64 });
      cleanup = result.cleanup;
      const data = new Uint8Array(result.analyser.frequencyBinCount);
      const draw = () => {
        result.analyser.getByteFrequencyData(data);
        setBars(Array.from({ length: 12 }, (_, i) => 2 + ((data[i + 1] ?? 0) / 255) * 27));
        frame = requestAnimationFrame(draw);
      };
      draw();
    });
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      void cleanup?.();
    };
  }, [track, muted]);
  if (!track || muted) {
    return <span className="text-xs text-cyan-100/70">Microphone waveform unavailable</span>;
  }
  return (
    <svg
      aria-label="Live Veteran microphone waveform"
      role="img"
      viewBox="0 0 120 36"
      className="h-9 w-32 text-cyan-300"
    >
      {bars.map((height, i) => (
        <rect
          key={i}
          x={i * 10 + 2}
          y={(36 - height) / 2}
          width="5"
          height={height}
          rx="2"
          fill="currentColor"
        />
      ))}
    </svg>
  );
}

const STATUS: Record<string, string> = {
  checking: "Checking voice readiness",
  unconfigured: "Sandbox voice gateway is not configured",
  authorization_required: "Private demo access is required",
  unavailable: "Voice transport is unavailable",
  ready: "Ready for your call",
  starting: "Creating your call",
  joining: "Connecting microphone",
  live: "Connected",
  ending: "Ending call",
  error: "Could not establish the call",
};

export type ScreenACall = ReturnType<typeof useOneClickCall>;
export function ScreenAVoice({
  onSession,
  onEnded,
  onCallState,
  onPreparing,
  onTranscript,
  onAfterCall,
}: {
  onSession: (session: CallSession, accessCode?: string, guestToken?: string) => void;
  onEnded: () => void;
  onCallState?: (phase: ScreenACall["phase"], agentAudio: boolean) => void;
  onPreparing?: (preparing: boolean) => void;
  onTranscript?: (lines: LiveTranscriptLine[]) => void;
  onAfterCall?: (result: AfterCall | null, retry: () => void) => void;
}) {
  const call = useOneClickCall({ onSession, onEnded });
  const [operatorCodeInput, setOperatorCodeInput] = useState("");
  const [typedReply, setTypedReply] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [escalationExpanded, setEscalationExpanded] = useState(false);
  const active = call.phase === "live";
  const canStart = call.phase === "ready" || call.phase === "error";
  const starting = ["starting", "joining"].includes(call.phase);
  const state: AgentState = active
    ? call.agentSpeaking
      ? "speaking"
      : call.agentTrack
        ? "listening"
        : "connecting"
    : starting || call.phase === "checking"
      ? "connecting"
      : call.phase === "ready"
        ? "idle"
        : "disconnected";

  useEffect(
    () => onCallState?.(call.phase, call.averyAudio),
    [call.phase, call.averyAudio, onCallState],
  );
  useEffect(() => onPreparing?.(call.agentPreparing), [call.agentPreparing, onPreparing]);
  useEffect(() => onTranscript?.(call.transcript), [call.transcript, onTranscript]);
  useEffect(
    () => onAfterCall?.(call.afterCall, call.retryAfterCall),
    [call.afterCall, call.retryAfterCall, onAfterCall],
  );

  return (
    <section
      aria-label="Live Voice"
      className="msa-workspace-voice flex h-full min-h-[350px] flex-col overflow-hidden rounded-xl border border-[#28466B] bg-[#162e51] text-white shadow-[0_8px_30px_rgba(22,46,81,0.12)]"
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Live Voice</h2>
          <p className="mt-1 text-xs text-slate-300">Veteran ↔ Avery · Browser microphone</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-xs">
          <span className={`size-2 rounded-full ${active ? "bg-emerald-300" : "bg-slate-400"}`} />
          {active ? "Media connected" : "Not connected"}
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col px-4 pb-4 pt-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold tracking-wide text-cyan-200">AVERY</span>
          <span aria-live="polite" className="text-slate-300">
            {active
              ? call.agentSpeaking
                ? "Speaking"
                : call.averyAudio
                  ? "Listening"
                  : "Joining call"
              : "Standby"}
          </span>
        </div>
        <div className="relative my-1 flex min-h-[90px] flex-1 items-center justify-center overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_center,rgba(0,189,227,0.12),transparent_68%)]">
          <ClientOnly fallback={<AudioLines className="size-16 text-violet-300" />}>
            <Suspense fallback={<AudioLines className="size-16 text-violet-300" />}>
              <div className="motion-reduce:hidden">
                <ScreenAOrb state={state} audioTrack={call.agentTrack ?? undefined} />
              </div>
              <span className="hidden motion-reduce:block" aria-label={`Avery ${state}`}>
                <AudioLines className="size-16 text-violet-300" />
              </span>
            </Suspense>
          </ClientOnly>
        </div>
        <div className="mb-2 flex items-center justify-between rounded-lg border border-cyan-300/20 bg-white/5 px-3 py-2">
          <div>
            <p className="text-sm font-semibold">Veteran</p>
            <p className="text-xs text-cyan-200">
              {call.muted
                ? "Mic muted"
                : call.veteranSpeaking
                  ? "Speaking"
                  : active
                    ? "Listening"
                    : "Awaiting call"}
            </p>
          </div>
          <MicWave track={call.microphoneTrack} muted={call.muted} />
        </div>
        <p role="status" className="mb-2 text-center text-xs text-slate-200">
          {STATUS[call.phase] ?? call.phase}
          {active && (call.averyAudio ? " · Avery audio available" : " · Waiting for Avery audio")}
        </p>
        {active && call.privateIdentity.required && (
          <PrivateIdentityField {...call.privateIdentity} />
        )}
        {active && !call.privateIdentity.required && (
          <details className="mb-3 rounded-lg border border-white/20 p-3">
            <summary className="cursor-pointer text-sm font-semibold">
              Having trouble being heard? Type a reply
            </summary>
            <p className="my-2 text-xs text-slate-200">
              You can speak slowly, spell a name, or type your answer here. Avery will use the same
              verification checks.
            </p>
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                setSendingReply(true);
                try {
                  if (await call.sendTypedReply(typedReply)) setTypedReply("");
                } finally {
                  setSendingReply(false);
                }
              }}
            >
              <label htmlFor="caller-typed-reply" className="text-xs">
                Your reply to Avery
              </label>
              <input
                id="caller-typed-reply"
                value={typedReply}
                maxLength={512}
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setTypedReply(e.target.value)}
                className="my-2 w-full rounded-md p-2 text-slate-900 bg-white"
              />
              <Button type="submit" disabled={sendingReply || !typedReply.trim()}>
                {sendingReply ? "Sending…" : "Send reply"}
              </Button>
            </form>
          </details>
        )}
        {call.phase === "authorization_required" ? (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              const value = operatorCodeInput.trim();
              if (!value) return;
              // Operator code stays in the existing in-memory call hook, never storage.
              call.setAccessCode(value);
              setOperatorCodeInput("");
            }}
          >
            <label
              htmlFor="msa-operator-code"
              className="block text-xs font-semibold text-cyan-100"
            >
              Private demo access code
            </label>
            <div className="flex gap-2">
              <input
                id="msa-operator-code"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={operatorCodeInput}
                onChange={(event) => setOperatorCodeInput(event.target.value)}
                placeholder="Enter operator code"
                className="min-w-0 flex-1 rounded-md border border-white/30 bg-white px-3 py-2 text-sm text-[#162e51] placeholder:text-slate-500"
              />
              <Button
                type="submit"
                disabled={!operatorCodeInput.trim()}
                className="bg-[#005ea2] text-white hover:bg-[#1a4480]"
              >
                Connect
              </Button>
            </div>
            <p className="text-xs text-slate-300">
              Authorized synthetic demo only. Credentials are not saved.
            </p>
          </form>
        ) : canStart ? (
          <Button
            className="min-h-11 w-full gap-2 rounded-lg bg-[#005ea2] text-sm font-semibold text-white hover:bg-[#1a4480]"
            onClick={() => void call.start()}
          >
            <PhoneCall className="size-4" />
            Call in Browser
          </Button>
        ) : active || starting ? (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="min-h-11 flex-1 gap-2 border-white/25 bg-white/10 text-white hover:bg-white/20 hover:text-white"
              disabled={!active || call.privateIdentity.required}
              onClick={() => void call.toggleMute()}
            >
              {call.muted ? <Mic className="size-4" /> : <MicOff className="size-4" />}
              {call.muted ? "Unmute Mic" : "Mute Mic"}
            </Button>
            <Button
              className="min-h-11 flex-1 gap-2 bg-red-700 text-white hover:bg-red-800"
              onClick={() => void call.hangUp()}
            >
              <PhoneOff className="size-4" />
              End Call
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            className="min-h-12 w-full gap-2 border-white/25 bg-white/10 text-white hover:bg-white/20 hover:text-white"
            onClick={call.retryStatus}
          >
            <RefreshCw className="size-4" />
            Retry Voice Connection
          </Button>
        )}
        {call.notice && (
          <p role="status" className="mt-3 text-sm text-amber-200">
            {call.notice}
          </p>
        )}
        {call.error && (
          <p role="alert" className="mt-3 text-sm text-amber-200">
            {call.error}
          </p>
        )}
        <div className="mt-3 rounded-md border border-white/15 bg-white/5">
          <button
            type="button"
            aria-expanded={escalationExpanded}
            onClick={() => setEscalationExpanded((value) => !value)}
            className="flex min-h-10 w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-cyan-100"
          >
            <span className="inline-flex items-center gap-2">
              <ShieldAlert className="size-4" /> Escalation Options
            </span>
            <ChevronDown
              className={`size-4 transition-transform ${escalationExpanded ? "rotate-180" : ""}`}
            />
          </button>
          {escalationExpanded && (
            <div className="space-y-2 border-t border-white/10 px-3 py-3 text-xs text-slate-200">
              <p>
                <Headset className="mr-1 inline size-4" /> Ask Avery for staff assistance; transfer
                requires verified staff media.
              </p>
              <p>
                <ClipboardList className="mr-1 inline size-4" /> Unsupported or blocked scheduling
                requests require manual review.
              </p>
              <p>These are guidance options, not fabricated handoff controls.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
