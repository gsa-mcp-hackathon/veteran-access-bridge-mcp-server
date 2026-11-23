import { lazy, Suspense, useState } from "react";
import { ClientOnly } from "@tanstack/react-router";
import type { AgentState } from "@livekit/components-react";
import { MicOff, Headphones, PhoneForwarded, Pause, PhoneOff, AudioLines } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import type { Live } from "./use-live";
import type { LiveMonitor } from "./use-live-monitor";
import { CallerAudioWave, phaseLabel } from "./live-monitor-panels";

const AveryAura = lazy(() => import("./avery-aura"));

function AuraFallback() {
  return (
    <div
      className="grid size-14 sm:size-[72px] min-[1100px]:size-[84px] place-items-center rounded-full border border-header-foreground/30 bg-canvas-raised text-header-foreground"
      aria-hidden="true"
    >
      <AudioLines className="size-6" />
    </div>
  );
}

function CallerFigure() {
  return (
    <svg
      viewBox="0 0 88 88"
      className="caller-figure size-14 sm:size-[72px] min-[1100px]:size-[78px]"
      aria-hidden="true"
    >
      <circle
        cx="44"
        cy="44"
        r="42"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.5"
      />
      <circle cx="44" cy="34" r="13" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path
        d="M20 72c3-14 13-21 24-21s21 7 24 21"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Static SVG waveform. Not audio-reactive: no human track exists in replay. */
function StaticWave() {
  const bars = [6, 12, 18, 10, 22, 14, 8, 16, 20, 9, 13, 6];
  return (
    <svg
      viewBox="0 0 96 24"
      className="caller-figure h-4 w-16 sm:h-5 sm:w-20 min-[1100px]:h-6 min-[1100px]:w-24"
      aria-hidden="true"
    >
      {bars.map((h, i) => (
        <rect
          key={i}
          x={i * 8 + 1}
          y={12 - h / 2}
          width="4"
          height={h}
          rx="2"
          fill="currentColor"
        />
      ))}
    </svg>
  );
}

function auraState(live: Live, monitor?: LiveMonitor): AgentState {
  if (monitor) {
    if (monitor.phase === "connected") return monitor.agentTrack ? "listening" : "idle";
    if (
      monitor.phase === "authorizing" ||
      monitor.phase === "connecting" ||
      monitor.phase === "reconnecting"
    )
      return "connecting";
    return "disconnected";
  }
  if (live.voice === "disconnected") return "disconnected";
  return "idle";
}

export function VoiceCall({
  live,
  exception,
  joinReady,
  duration,
  ownership,
  onMonitor,
  onJoin,
  monitor,
  showControls = true,
}: {
  showControls?: boolean;
  monitor?: LiveMonitor | undefined;
  live: Live;
  exception: boolean;
  joinReady: boolean;
  duration: string;
  ownership: string;
  onMonitor: () => void;
  onJoin: () => void;
}) {
  const [ending, setEnding] = useState(false);
  const [notice, setNotice] = useState("");
  const ended = !monitor && live.voice === "disconnected";
  const observer = !!monitor;
  const quiet =
    "min-h-11 gap-1 sm:gap-1.5 border-header-foreground/40 bg-transparent h-auto flex-col px-1 py-1 text-xs sm:h-9 sm:flex-row sm:px-3 sm:py-0 sm:text-sm text-header-foreground hover:bg-canvas-raised hover:text-header-foreground";
  return (
    <section
      aria-label="Synthetic voice call"
      className="rounded-lg border border-header bg-header p-3 text-header-foreground shadow-sm sm:p-4 min-[1100px]:px-5 min-[1100px]:py-5"
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3 min-[1100px]:flex-col min-[1100px]:gap-2 min-[1100px]:text-center">
          <span className="shrink-0">
            <CallerFigure />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold sm:text-base">Veteran Caller</p>
            <p className="text-xs text-canvas-muted">
              {monitor
                ? monitor.callerTrack
                  ? "Caller audio subscribed"
                  : "No caller audio track"
                : "Synthetic participant"}
            </p>
            <div
              className="mt-1"
              aria-label={
                monitor?.callerTrack
                  ? "Caller waveform · driven by subscribed LiveKit audio"
                  : "Static waveform · no audio track"
              }
            >
              {monitor ? (
                monitor.callerTrack ? (
                  <CallerAudioWave track={monitor.callerTrack} />
                ) : (
                  <span className="text-xs text-canvas-muted">Awaiting live caller audio</span>
                )
              ) : (
                <StaticWave />
              )}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2 sm:gap-3 min-[1100px]:flex-col min-[1100px]:gap-2 min-[1100px]:text-center">
          <div
            className="shrink-0"
            role="img"
            aria-label={
              monitor
                ? `Avery voice visualizer · ${phaseLabel(monitor.phase)}${monitor.agentTrack ? " · agent audio track bound" : " · no agent audio track"}`
                : "Avery voice visualizer · scripted replay, no LiveKit connection"
            }
          >
            <ClientOnly fallback={<AuraFallback />}>
              <Suspense fallback={<AuraFallback />}>
                <span className="motion-reduce:hidden">
                  <AveryAura
                    state={auraState(live, monitor)}
                    audioTrack={monitor?.agentTrack ?? undefined}
                  />
                </span>
                <span className="hidden motion-reduce:block">
                  <AuraFallback />
                </span>
              </Suspense>
            </ClientOnly>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold sm:text-base">Avery</p>
            <p className="text-xs text-canvas-muted">
              {monitor
                ? phaseLabel(monitor.phase)
                : ended
                  ? "Disconnected"
                  : live.joined
                    ? "Assistant / copilot"
                    : `Simulated ${live.voice}`}
            </p>
          </div>
        </div>
      </div>
      <div className="mt-3 border-t min-[1100px]:mt-4 border-header-foreground/20 pt-3">
        <p className="sr-only">
          Current call {duration}. {ended ? "Session ended" : ownership}.
        </p>
        {showControls ? (
          <>
            <div className="grid grid-cols-5 gap-1 sm:flex sm:flex-wrap sm:items-center sm:gap-2">
              <span className="mr-1 hidden font-mono text-sm sm:block" aria-hidden="true">
                {duration}
              </span>
              <Button
                variant="outline"
                className={quiet}
                disabled={observer}
                title={
                  observer
                    ? "Mute · observer cannot publish audio"
                    : "Mute · unsupported in replay (no microphone)"
                }
                onClick={() =>
                  setNotice("Mute is unsupported: no microphone capture or real media in replay.")
                }
              >
                <MicOff className="size-4" />
                Mute
              </Button>
              <Button
                variant="outline"
                className={quiet}
                disabled={ended || (observer && monitor?.phase !== "connected")}
                aria-pressed={observer ? monitor?.monitoring : undefined}
                title={
                  observer
                    ? "Monitor · local playback of subscribed audio"
                    : "Monitor · synthetic only"
                }
                onClick={() => {
                  if (monitor) {
                    const next = !monitor.monitoring;
                    void monitor.setMonitoring(next);
                    setNotice(
                      next
                        ? "Playing subscribed LiveKit audio locally. Observer only; nothing is published."
                        : "Local playback stopped.",
                    );
                    return;
                  }
                  if (exception) onMonitor();
                  setNotice(
                    "Synthetic monitoring only. No audio connection or ownership acceptance.",
                  );
                }}
              >
                <Headphones className="size-4" />
                Monitor
              </Button>
              <Button
                variant={joinReady && !ended ? "default" : "outline"}
                className={
                  joinReady && !ended
                    ? "min-h-11 gap-1 sm:gap-1.5 h-auto flex-col px-1 py-1 text-xs sm:h-9 sm:flex-row sm:px-3 sm:py-0 sm:text-sm"
                    : quiet
                }
                disabled={observer || ended || !joinReady}
                aria-describedby="join-guard"
                title={
                  joinReady
                    ? "Join · opens handoff review"
                    : "Join requires a synthetic handoff request"
                }
                onClick={onJoin}
              >
                <PhoneForwarded className="size-4" />
                Join
              </Button>
              <Button
                variant="outline"
                className={quiet}
                disabled={observer}
                title={
                  observer
                    ? "Hold · no gateway acknowledgment available"
                    : "Hold · unsupported by replay transport"
                }
                onClick={() =>
                  setNotice("Hold is unsupported by local replay. No real call is placed on hold.")
                }
              >
                <Pause className="size-4" />
                Hold
              </Button>
              <Button
                variant="outline"
                className="min-h-11 sm:ml-auto gap-1 sm:gap-1.5 border-2 border-destructive-light bg-transparent h-auto flex-col px-1 py-1 text-xs sm:h-9 sm:flex-row sm:px-3 sm:py-0 sm:text-sm font-semibold text-destructive-light hover:bg-destructive hover:text-destructive-foreground"
                disabled={ended || observer}
                title={
                  observer
                    ? "End call · unavailable to observer; use Disconnect monitor"
                    : "End · requires confirmation"
                }
                onClick={() => setEnding(true)}
              >
                <PhoneOff className="size-4" />
                End
              </Button>
            </div>
            <p id="join-guard" role="status" className="mt-2 text-xs text-canvas-muted">
              {notice ||
                (observer
                  ? "Subscribe-only observer. Join, Hold and End are unavailable; Disconnect monitor is in Demo controls."
                  : joinReady
                    ? "Join opens the synthetic handoff review. No real media."
                    : "Join is available only after a synthetic handoff request. No real call controls.")}
            </p>
          </>
        ) : (
          <p
            role="status"
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-canvas-muted"
          >
            <span className="font-mono text-sm text-header-foreground">{duration}</span>
            <span>{ended ? "Session ended" : ownership}</span>
            <span>
              {observer
                ? `Observer · subscribe-only${monitor?.monitoring ? " · local playback on" : ""}`
                : "Scripted replay · no LiveKit connection"}
            </span>
          </p>
        )}
      </div>
      <Sheet open={ending} onOpenChange={setEnding}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetTitle>End synthetic session?</SheetTitle>
          <SheetDescription>
            Stops local replay only. Unresolved handoff requests remain available for safe fallback
            and closure.
          </SheetDescription>
          <div className="mt-6 flex gap-2">
            <Button
              variant="destructive"
              className="min-h-11"
              onClick={() => {
                live.end();
                setEnding(false);
              }}
            >
              Confirm end simulation
            </Button>
            <Button variant="outline" className="min-h-11" onClick={() => setEnding(false)}>
              Cancel
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
