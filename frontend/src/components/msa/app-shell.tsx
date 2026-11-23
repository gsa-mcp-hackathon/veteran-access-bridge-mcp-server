import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Play, Pause, RotateCcw, ArrowUpRight, Inbox, PhoneCall } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLive } from "./use-live";
import { useHandoffDemo } from "./use-handoff";
import {
  HandoffCenter,
  HandoffControls,
  HandoffIndicators,
  SafeHandoffContext,
} from "./handoff-panels";
import {
  HANDOFF_SCENARIOS,
  needsAttention,
  ownershipLabel,
  type HandoffScenario,
} from "@/lib/handoff";
import { emptyEncounter, type Message } from "@/lib/scenario";
import { EncounterScheduling } from "./encounter-scheduling";
import { EncounterWork } from "./encounter-work";
import { VoiceCall } from "./voice-call";
import { useLiveMonitor } from "./use-live-monitor";
import { LiveEvidence, LiveMonitorConnect, phaseLabel } from "./live-monitor-panels";
import { stepsFromMonitor, stepsFromReplay } from "@/lib/mcp-execution";
import { AwaitingEvidence, LiveConversation, McpInspector, WorkflowSteps } from "./command-center";

export function MSAAppShell() {
  // Live observer is the default. Replay is a separate, explicitly selected demo.
  const [mode, setMode] = useState<"live" | "replay">("live");
  const authoritative = mode === "live";
  const demo = useHandoffDemo(!authoritative);
  const appointment = useLive("success", !authoritative);
  const monitor = useLiveMonitor();
  const [generation, setGeneration] = useState(0);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"inbox" | "review">("inbox");
  const [focus, setFocus] = useState<{ id: string } | null>(null);
  const [calendarFrom, setCalendarFrom] = useState<Date | null>(null);
  useEffect(() => setCalendarFrom(new Date()), []);
  const inboxTrigger = useRef<HTMLButtonElement>(null);
  const attention = authoritative ? 0 : demo.records.filter(needsAttention).length;
  const exception = demo.selected !== "success";
  const review = () => {
    setTab("review");
    setOpen(true);
  };
  const handoffMessages: Message[] = [
    {
      id: "ho-m1",
      speaker: "avery",
      time: "13:45:01",
      text: "This is a synthetic primary care scheduling conversation. How can I help?",
    },
    {
      id: "ho-m2",
      speaker: "veteran",
      time: "13:45:02",
      text: "I need primary care help. Morning and in person would be best.",
    },
    ...(demo.state.step >= 3
      ? [
          {
            id: "ho-m3",
            speaker: "avery" as const,
            time: "13:45:03",
            text: "The identity check did not match. Scheduling details remain hidden. A scheduler review is needed; requesting help does not transfer the session.",
          },
        ]
      : []),
    ...demo.state.audit
      .filter((event) => event.event === "handoff.joined")
      .slice(0, 1)
      .map((event) => ({
        id: `ho-msa-${event.id}`,
        speaker: "msa" as const,
        time: event.time,
        text: "I have joined this simulated session to assist with verification. Avery remains my copilot. (Historical UI fixture; no audio speech.)",
      })),
  ];
  const live = exception
    ? {
        ...appointment,
        voice:
          demo.state.media === "disconnected" || demo.state.media === "ended"
            ? ("disconnected" as const)
            : demo.state.requestId
              ? ("awaiting" as const)
              : ("listening" as const),
        messages: demo.state.step ? handoffMessages : [],
        events: demo.state.audit.map((event) => ({
          id: event.id,
          label: `${event.event} · ${event.detail}`,
          status: "completed" as const,
          time: event.time,
        })),
        enc: emptyEncounter(),
        slots: [],
        playing: demo.state.playing,
        joined: demo.state.joined,
        end: () => demo.dispatch({ type: "end" }),
        setPlaying: (value: boolean) => demo.dispatch({ type: "play", value }),
        approve: () => {},
        decline: () => {},
        setJoined: () => {},
      }
    : appointment;
  const steps = useMemo(
    () =>
      authoritative
        ? stepsFromMonitor(monitor.projection?.events ?? [])
        : exception
          ? []
          : stepsFromReplay(live.events),
    [authoritative, monitor.projection, exception, live.events],
  );
  const duration = authoritative
    ? "--:--"
    : live.messages.length
      ? `${String(Math.floor((live.messages.length * 7) / 60)).padStart(2, "0")}:${String((live.messages.length * 7) % 60).padStart(2, "0")}`
      : "00:00";
  const status = authoritative
    ? `Authoritative monitor · ${phaseLabel(monitor.phase)}`
    : exception
      ? ownershipLabel(demo.state)
      : live.enc.booked
        ? "Simulated booking complete · no MSA action"
        : "Avery Handling (Autonomous)";
  return (
    <div className="min-h-screen bg-background">
      <header className="grid min-h-[75px] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 bg-header px-3 py-2 text-header-foreground sm:px-4 lg:flex lg:flex-wrap lg:gap-x-6">
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-tight">Veteran Access Bridge</p>
          <h1 className="text-base font-semibold leading-tight sm:text-lg">
            Autonomous Scheduling Command Center
          </h1>
          <p className="text-xs text-canvas-muted">Primary Care · MCP-Powered</p>
        </div>
        <div className="col-span-2 row-start-2 flex min-w-0 flex-col gap-1 lg:row-auto">
          <p className="text-sm" role="status">
            {authoritative ? (monitor.projection?.case_id ?? "No active session") : "SYN-00418"} ·{" "}
            {status} · <span className="font-mono">{duration}</span>
          </p>
          <span className="w-fit rounded-sm bg-sandbox px-2 py-0.5 text-xs font-bold text-sandbox-foreground">
            {authoritative
              ? `SANDBOX · Live observer · ${monitor.phase === "connected" ? "LiveKit connected" : "LiveKit not connected"}`
              : "SANDBOX · Explicit scripted replay · NO LiveKit audio connection"}
            <span className="hidden font-semibold sm:inline">
              {" "}
              · Synthetic demo / no production changes
            </span>
          </span>
        </div>
        <div className="col-start-2 row-start-1 flex items-center gap-0.5 lg:ml-auto">
          {!authoritative && (
            <>
              <Button
                ref={inboxTrigger}
                variant="ghost"
                size="icon"
                className="relative size-11 text-header-foreground hover:bg-canvas-raised hover:text-header-foreground"
                aria-label={
                  attention ? `Handoff inbox, ${attention} need attention` : "Handoff inbox"
                }
                title="Handoff inbox"
                onClick={() => {
                  setTab("inbox");
                  setOpen(true);
                }}
              >
                <Inbox />
                {attention > 0 && (
                  <span
                    aria-hidden="true"
                    className="absolute right-1 top-1 grid min-w-4 place-items-center rounded-full bg-sandbox px-1 text-[11px] font-bold leading-4 text-sandbox-foreground"
                  >
                    {attention}
                  </span>
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-11 text-header-foreground hover:bg-canvas-raised hover:text-header-foreground"
                aria-label={live.playing ? "Pause replay" : "Play replay"}
                title={live.playing ? "Pause replay" : "Play replay"}
                disabled={live.voice === "disconnected" || (!exception && live.enc.booked)}
                onClick={() => live.setPlaying(!live.playing)}
              >
                {live.playing ? <Pause /> : <Play />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-11 text-header-foreground hover:bg-canvas-raised hover:text-header-foreground"
                aria-label="Restart replay"
                title="Restart replay"
                onClick={() => {
                  if (exception) demo.reset();
                  else appointment.reset();
                  setGeneration((old) => old + 1);
                  setFocus(null);
                }}
              >
                <RotateCcw />
              </Button>
            </>
          )}
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="size-11 text-header-foreground hover:bg-canvas-raised hover:text-header-foreground"
            title="Design system"
          >
            <Link to="/design-system" aria-label="Design system">
              <ArrowUpRight />
            </Link>
          </Button>
          {!authoritative && (
            <span className="ml-2 hidden text-sm xl:block">
              <span className="block text-xs text-canvas-muted">Signed in (demo)</span>
              MSA J. Rivera
            </span>
          )}
        </div>
      </header>
      {!authoritative && (
        <HandoffCenter
          demo={demo}
          open={open}
          onOpenChange={setOpen}
          tab={tab}
          onTabChange={setTab}
          triggerRef={inboxTrigger}
        />
      )}
      <section
        aria-label="Observer connection"
        className="flex flex-wrap items-center justify-between gap-3 border-b bg-surface px-4 py-3 text-sm"
      >
        {authoritative ? (
          <>
            <p className="text-muted-foreground">
              Live observer only · {phaseLabel(monitor.phase)} · No simulated activity
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Button asChild className="min-h-11 gap-2">
                <Link to="/demo-call">
                  <PhoneCall className="size-4" aria-hidden="true" />
                  Talk with Avery
                </Link>
              </Button>
              <span className="text-xs text-muted-foreground">
                IBM native chat + voice · Veteran session opens separately
              </span>
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">
                  Advanced connection
                </summary>
                <div className="mt-2 flex flex-wrap items-end gap-2">
                  <LiveMonitorConnect monitor={monitor} />
                </div>
              </details>
              {monitor.phase === "connected" && (
                <Button
                  variant="outline"
                  className="min-h-11"
                  aria-pressed={monitor.monitoring}
                  onClick={() => void monitor.setMonitoring(!monitor.monitoring)}
                >
                  {monitor.monitoring ? "Stop local playback" : "Play observer audio locally"}
                </Button>
              )}
            </div>
          </>
        ) : (
          <>
            <p className="text-muted-foreground">
              Scripted demo replay · No LiveKit connection or authoritative MCP results
            </p>
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => {
                appointment.setPlaying(false);
                setMode("live");
              }}
            >
              Return to live observer
            </Button>
          </>
        )}
      </section>
      <main className="encounter-console command-center p-3 sm:p-4">
        <div className="console-col flex min-w-0 flex-col gap-3">
          <VoiceCall
            key={`${demo.selected}-${generation}`}
            live={live}
            exception={!authoritative && exception}
            joinReady={false}
            duration={duration}
            ownership={status}
            onMonitor={() => {}}
            monitor={authoritative ? monitor : undefined}
            onJoin={review}
            showControls={false}
          />
          <LiveConversation
            authoritative={authoritative}
            messages={authoritative ? [] : live.messages}
            steps={steps}
            slots={authoritative ? [] : live.slots}
            showCalendar={!authoritative && !exception && live.enc.verified && live.enc.evaluated}
            calendarFrom={calendarFrom ?? new Date(0)}
            onFocusStep={(id) => setFocus({ id })}
            emptyLabel={
              authoritative
                ? "Awaiting authoritative MCP events · connect a live synthetic Veteran session"
                : live.voice === "disconnected"
                  ? "Replay ended. No conversation turns recorded."
                  : "Waiting for the first scripted turn…"
            }
          />
        </div>
        <div className="console-col flex min-w-0 flex-col gap-3">
          <McpInspector
            steps={steps}
            authoritative={authoritative}
            focusId={focus?.id ?? null}
            key={`${demo.selected}-${generation}`}
            caseId={authoritative ? (monitor.projection?.case_id ?? "Unavailable") : "SYN-00418"}
            correlationId={
              authoritative
                ? (monitor.projection?.correlation_id ?? null)
                : (steps[0]?.correlationId ?? null)
            }
          />
        </div>
        <div className="console-col flex min-w-0 flex-col gap-3 overflow-y-auto">
          {authoritative ? (
            <>
              <LiveEvidence monitor={monitor} />
              <div className="console-card pb-3">
                <WorkflowSteps
                  verified={false}
                  searched={false}
                  selected={false}
                  booked={false}
                  authoritative
                />
                <AwaitingEvidence label="No booking, documents or notifications shown without canonical case-scoped evidence." />
              </div>
            </>
          ) : exception ? (
            <div className="console-card">
              <HandoffIndicators state={demo.state} />
              <SafeHandoffContext state={demo.state} onReview={review} />
              <p className="p-4 text-sm text-muted-foreground">
                Avery's Work is blocked. No protected artifacts or booking are available.
              </p>
            </div>
          ) : (
            <>
              <div className="console-card overflow-hidden">
                <EncounterScheduling live={live} />
              </div>
              <div className="console-card overflow-hidden">
                <WorkflowSteps
                  verified={live.enc.verified}
                  searched={live.enc.slotsLoaded}
                  selected={!!live.enc.selectedId}
                  booked={live.enc.booked}
                  authoritative={false}
                />
                <EncounterWork key={generation} live={live} />
              </div>
            </>
          )}
        </div>
      </main>
      <details className="border-t bg-surface px-4">
        <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium">
          Advanced · developer scripted replay (not live)
        </summary>
        {authoritative ? (
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 text-sm">
            <p className="text-muted-foreground">
              Replay is off by default. Starting a demo disconnects any real observer.
            </p>
            <Button
              variant="outline"
              className="min-h-11"
              onClick={() => {
                monitor.disconnect();
                demo.select("success");
                appointment.reset();
                setMode("replay");
              }}
            >
              Start scripted replay (demo only)
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 pb-3 text-sm">
            <label className="flex max-w-full flex-col gap-1">
              Synthetic scenario replay
              <select
                aria-label="Synthetic scenario replay"
                value={demo.selected}
                onChange={(event) => {
                  const value = event.target.value;
                  if (HANDOFF_SCENARIOS.some((scenario) => scenario.id === value))
                    demo.select(value as HandoffScenario);
                  setOpen(false);
                }}
                className="min-h-11 max-w-full rounded-md border bg-surface px-2 text-sm"
              >
                {HANDOFF_SCENARIOS.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.label}
                  </option>
                ))}
              </select>
            </label>
            {exception && <HandoffControls demo={demo} />}
          </div>
        )}
      </details>
    </div>
  );
}
