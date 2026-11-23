import { useCallback, useEffect, useMemo, useState } from "react";
import { Radio } from "lucide-react";
import type { AfterCall } from "@/lib/after-call";
import { ReviewerSignOut } from "./reviewer-sign-out";
import type { CallPhase, CallSession, LiveTranscriptLine } from "./use-one-click-call";
import { ScreenAVoice } from "./screen-a-voice";
import { AfterCallWork } from "./screen-a-after-call";
import { screenAEvidence } from "./screen-a-evidence";
import { useLiveMonitor } from "./use-live-monitor";
import { stepsFromMonitor } from "@/lib/mcp-execution";
import {
  LiveConversationFeed,
  SchedulingEncounterSummary,
  UnifiedWorkflowStepper,
} from "./unified-workspace-panels";

export function AutonomousScreenA() {
  const monitor = useLiveMonitor();
  const { connect, connectGuestActivity, stop } = monitor;
  const [session, setSession] = useState<CallSession | null>(null);
  const [callPhase, setCallPhase] = useState<CallPhase>("checking");
  const [agentAudio, setAgentAudio] = useState(false);
  const [agentPreparing, setAgentPreparing] = useState(false);
  const [transcript, setTranscript] = useState<LiveTranscriptLine[]>([]);
  const [ended, setEnded] = useState(false);
  const [wrapup, setWrapup] = useState<{ result: AfterCall | null; retry: () => void }>({
    result: null,
    retry: () => {},
  });
  const onAfterCall = useCallback(
    (result: AfterCall | null, retry: () => void) => setWrapup({ result, retry }),
    [],
  );
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const steps = useMemo(
    () => stepsFromMonitor(monitor.projection?.events ?? []),
    [monitor.projection?.events],
  );
  const events = monitor.projection?.events ?? [];
  const crmReceipts = events.flatMap((event) =>
    event.crm_receipt && event.crm_receipt.voice_session_id === session?.voice_session_id
      ? [event.crm_receipt]
      : [],
  );
  const bookingProof =
    events
      .filter((event) => event.voice_booking?.voice_session_id === session?.voice_session_id)
      .at(-1)?.voice_booking ?? null;
  const evidence = screenAEvidence(callPhase, agentAudio, events, steps, ended);
  useEffect(() => {
    if (callPhase !== "live" || startedAt === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [callPhase, startedAt]);
  const elapsed =
    startedAt === null
      ? "00:00"
      : (() => {
          const duration = Math.max(0, Math.floor((now - startedAt) / 1000));
          return `${String(Math.floor(duration / 60)).padStart(2, "0")}:${String(duration % 60).padStart(2, "0")}`;
        })();
  const onSession = useCallback(
    (ids: CallSession, accessCode?: string, guestToken?: string) => {
      setSession(ids);
      setStartedAt(Date.now());
      setNow(Date.now());
      setEnded(false);
      // A hosted guest sees only their own sanitized event metadata; unlike a
      // scheduler this does not connect a second LiveKit observer/audio leg.
      // Never block the Veteran's active audio call if activity is unavailable.
      if (guestToken) {
        connectGuestActivity({
          caseId: ids.case_id,
          interactionId: ids.interaction_id,
          voiceSessionId: ids.voice_session_id,
          guestToken,
        });
      } else {
        void connect({
          caseId: ids.case_id,
          voiceSessionId: ids.voice_session_id,
          ...(accessCode ? { accessCode } : {}),
          retryNotReady: true,
        });
      }
    },
    [connect, connectGuestActivity],
  );
  const onEnded = useCallback(() => {
    setEnded(true);
    setStartedAt(null);
    stop();
    // Leave read-only projection available for after-call evidence review.
  }, [stop]);
  const onCallState = useCallback((phase: CallPhase, hasAudio: boolean) => {
    setCallPhase(phase);
    setAgentAudio(hasAudio);
  }, []);
  const mediaText =
    callPhase === "live"
      ? "LiveKit · Connected"
      : callPhase === "starting" || callPhase === "joining"
        ? "LiveKit · Connecting…"
        : "LiveKit · Disconnected";

  return (
    <div className="msa-workspace flex min-h-[100dvh] flex-col bg-[#f5f8fb] text-[#1b1b1b]">
      <header className="shrink-0 border-b-4 border-[#00bde3] bg-[#162e51] px-4 py-3 text-white sm:px-6">
        <div className="mx-auto flex w-full flex-wrap items-center justify-between gap-x-8 gap-y-3">
          <div className="flex max-w-full items-center gap-3">
            <img src="/favicon.svg?v=2" alt="" className="size-10 shrink-0 sm:size-12" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold leading-tight tracking-tight sm:text-[28px]">
                Veteran Access Bridge MCP Server
              </h1>
              <p className="text-base font-semibold text-[#b9e8f6] sm:whitespace-nowrap sm:text-xl">
                Autonomous Scheduling Command Center
              </p>
              <p className="mt-1 text-xs text-blue-100/75">
                Voice-first appointment scheduling · MCP-powered
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
            <span
              role="status"
              className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1.5"
            >
              <Radio className="size-3.5" />
              {mediaText}
              {callPhase === "live" ? ` · ${elapsed}` : ""}
            </span>
            <span className="rounded-full border border-[#73b3e7]/50 bg-[#1a4480] px-3 py-1.5">
              Avery · Autonomous agent
            </span>
            <span className="rounded-md bg-amber-100 px-2.5 py-1.5 font-bold text-amber-950">
              Sandbox
            </span>
            <ReviewerSignOut
              callActive={
                callPhase === "live" || callPhase === "starting" || callPhase === "joining"
              }
            />
          </div>
        </div>
      </header>
      <main className="msa-workspace-main flex w-full flex-1 flex-col gap-3 p-3 lg:p-4">
        <UnifiedWorkflowStepper
          intake={evidence.intake}
          scheduling={evidence.scheduling}
          ended={ended}
          events={events}
        />
        <div className="msa-workspace-top grid min-w-0 items-stretch gap-3 lg:grid-cols-2 2xl:grid-cols-[minmax(240px,0.85fr)_minmax(420px,1.75fr)_minmax(280px,1fr)]">
          <ScreenAVoice
            onSession={onSession}
            onEnded={onEnded}
            onCallState={onCallState}
            onPreparing={setAgentPreparing}
            onTranscript={setTranscript}
            onAfterCall={onAfterCall}
          />
          <LiveConversationFeed
            agentPreparing={agentPreparing}
            transcript={transcript}
            steps={steps}
            events={events}
            callActive={callPhase === "live"}
            observerError={monitor.error}
            observerPhase={monitor.phase}
          />
          <div className="min-h-0 min-w-0 lg:col-span-2 2xl:col-span-1">
            <SchedulingEncounterSummary
              identityVerified={evidence.identityVerified}
              caseId={session?.case_id ?? null}
              bookingProof={bookingProof}
              appointmentOptions={
                events
                  .filter(
                    (event) =>
                      event.appointment_options?.voice_session_id === session?.voice_session_id,
                  )
                  .at(-1)?.appointment_options ?? null
              }
            />
          </div>
        </div>
        <div className="msa-workspace-after-call min-w-0">
          <AfterCallWork
            ended={ended}
            receipt={null}
            bookingProof={bookingProof}
            crmReceipts={crmReceipts}
            afterCall={wrapup.result}
            retryAfterCall={wrapup.retry}
          />
        </div>
        <p className="msa-workspace-disclaimer px-1 text-[10px] text-slate-500">
          Sandbox prototype · Synthetic only · Audio, transcript, MCP events, appointment selection
          and booking are distinct evidence sources.
        </p>
      </main>
    </div>
  );
}
