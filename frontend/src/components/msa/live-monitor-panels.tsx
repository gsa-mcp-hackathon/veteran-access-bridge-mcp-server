import { useEffect, useState } from "react";
import { friendlyToolName } from "@/lib/avery-tool-labels";
import type { RemoteAudioTrack } from "livekit-client";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import type { LiveMonitor } from "./use-live-monitor";
import type { MonitorProjection } from "@/lib/live-monitor";

export const TRANSCRIPT_UNAVAILABLE = "Voice transcript unavailable from authoritative source";

export function phaseLabel(phase: LiveMonitor["phase"]) {
  return {
    idle: "Not connected · awaiting a synthetic voice session",
    authorizing: "Authorizing monitor (sandbox gateway)",
    connecting: "Connecting to LiveKit (not yet connected)",
    connected: "LiveKit connected · subscribe-only observer",
    reconnecting: "LiveKit reconnecting",
    disconnected: "LiveKit disconnected",
    error: "Monitor error",
  }[phase];
}

const ID = /^[A-Za-z0-9_-]{1,64}$/;

export function LiveMonitorConnect({ monitor }: { monitor: LiveMonitor }) {
  const [open, setOpen] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [session, setSession] = useState("");
  const [accessCode, setAccessCode] = useState("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams(window.location.search);
    const proposedCase = query.get("case_id") ?? "";
    const proposedSession = query.get("voice_session_id") ?? "";
    if (ID.test(proposedCase)) setCaseId(proposedCase);
    if (ID.test(proposedSession)) setSession(proposedSession);
  }, []);
  const valid = ID.test(caseId) && ID.test(session) && accessCode.length >= 32;
  return (
    <div className="flex flex-col gap-1">
      <span>Authoritative monitor (sandbox only)</span>
      {monitor.active && monitor.phase !== "error" ? (
        <Button variant="outline" className="min-h-11" onClick={monitor.disconnect}>
          Disconnect observer
        </Button>
      ) : (
        <Button variant="outline" className="min-h-11" onClick={() => setOpen(true)}>
          {monitor.phase === "error" ? "Retry sandbox connection…" : "Connect sandbox…"}
        </Button>
      )}
      <Sheet
        open={open}
        onOpenChange={(value) => {
          setOpen(value);
          if (!value) setAccessCode("");
        }}
      >
        <SheetContent className="w-full sm:max-w-md">
          <SheetTitle>Connect authoritative monitor</SheetTitle>
          <SheetDescription>
            Local synthetic sandbox gateway only; not production MSA sign-in. Subscribe-only: no
            microphone, hold, transfer or call control. The access code is kept in memory only.
          </SheetDescription>
          <form
            className="mt-4 flex flex-col gap-3 text-sm"
            onSubmit={(event) => {
              event.preventDefault();
              if (!valid) return;
              void monitor.connect({ accessCode, caseId, voiceSessionId: session });
              setAccessCode("");
              setOpen(false);
            }}
          >
            <label className="flex flex-col gap-1">
              Case ID
              <input
                className="min-h-11 rounded-md border bg-surface px-2"
                value={caseId}
                onChange={(e) => setCaseId(e.target.value.trim())}
                autoComplete="off"
              />
            </label>
            <label className="flex flex-col gap-1">
              Voice session ID
              <input
                className="min-h-11 rounded-md border bg-surface px-2"
                value={session}
                onChange={(e) => setSession(e.target.value.trim())}
                autoComplete="off"
              />
            </label>
            <label className="flex flex-col gap-1">
              Operator access code
              <input
                type="password"
                className="min-h-11 rounded-md border bg-surface px-2"
                value={accessCode}
                onChange={(e) => setAccessCode(e.target.value)}
                autoComplete="off"
              />
            </label>
            <Button type="submit" className="min-h-11" disabled={!valid}>
              Connect
            </Button>
          </form>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export function LiveEventFeed({
  projection,
  view,
}: {
  projection: MonitorProjection | null;
  view: "conversation" | "activity" | "timeline";
}) {
  const events = projection?.events ?? [];
  return (
    <div className="h-full min-h-[420px] overflow-y-auto p-2 text-sm">
      {view === "conversation" && (
        <p role="status" className="mb-3 rounded-md border bg-surface p-3 font-medium">
          {TRANSCRIPT_UNAVAILABLE}
        </p>
      )}
      {view !== "conversation" &&
        (events.length === 0 ? (
          <p className="text-muted-foreground">Awaiting authoritative evidence</p>
        ) : (
          <ol aria-label="Authoritative events" className="flex flex-col gap-2">
            {events.map((e) => (
              <li key={e.event_id} className="rounded-md border bg-surface p-2">
                <p className="font-medium">
                  {e.event_type}
                  {e.tool_name ? ` · ${friendlyToolName(e.tool_name)}` : ""}
                  {e.status ? ` · ${e.status}` : ""}
                  {e.error_code ? ` · error ${e.error_code}` : ""}
                </p>
                <p className="text-xs text-muted-foreground">
                  {e.occurred_at} · {e.source} · correlation {e.correlation_id}
                </p>
              </li>
            ))}
          </ol>
        ))}
    </div>
  );
}

export function LiveEvidence({ monitor }: { monitor: LiveMonitor }) {
  const p = monitor.projection;
  return (
    <section aria-label="Scheduling encounter" className="console-card p-4 text-sm">
      <h2 className="font-semibold">Scheduling Encounter · Authoritative</h2>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <dt className="text-muted-foreground">Media</dt>
        <dd>{phaseLabel(monitor.phase)}</dd>
        <dt className="text-muted-foreground">Interaction status</dt>
        <dd>{p?.status ?? "Awaiting authoritative evidence"}</dd>
        <dt className="text-muted-foreground">Human control</dt>
        <dd>{p?.human_control_mode ?? "Awaiting authoritative evidence"}</dd>
        <dt className="text-muted-foreground">Correlation</dt>
        <dd className="break-all">{p?.correlation_id ?? "Awaiting authoritative evidence"}</dd>
      </dl>
      {monitor.error && (
        <p role="alert" className="mt-3 text-destructive">
          {monitor.error}
        </p>
      )}
      <p className="mt-3 text-muted-foreground">
        Appointment details, booking and letters are not shown: the authoritative feed provides no
        verified scheduling evidence here.
      </p>
    </section>
  );
}

export function LiveChatDisabled() {
  return (
    <aside
      aria-label="Private staff copilot"
      className="copilot-rail flex min-w-0 flex-col bg-surface"
    >
      <header className="bg-header px-4 py-3 text-header-foreground">
        <h2 className="font-semibold">Chat with Avery</h2>
        <p className="mt-1 text-xs text-canvas-muted">Unavailable in authoritative mode</p>
      </header>
      <p className="p-4 text-sm text-muted-foreground">
        No real staff channel exists yet. Private chat is disabled while monitoring.
      </p>
    </aside>
  );
}

/** Waveform driven by the actual subscribed caller audio via Web Audio analyser. */
export function CallerAudioWave({ track }: { track: RemoteAudioTrack }) {
  const [bars, setBars] = useState<number[]>(Array(12).fill(2));
  useEffect(() => {
    let raf = 0;
    let cleanup: (() => Promise<void>) | undefined;
    let cancelled = false;
    void import("livekit-client").then(({ createAudioAnalyser }) => {
      if (cancelled) return;
      const { analyser, cleanup: c } = createAudioAnalyser(track, { fftSize: 64 });
      cleanup = c;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        setBars(Array.from({ length: 12 }, (_, i) => 2 + ((data[i + 1] ?? 0) / 255) * 20));
        raf = requestAnimationFrame(tick);
      };
      tick();
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      void cleanup?.();
    };
  }, [track]);
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
