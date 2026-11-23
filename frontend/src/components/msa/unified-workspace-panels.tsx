import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Activity, CalendarDays, ChevronDown, Clock3, FileJson, Server } from "lucide-react";
import type { LiveTranscriptLine } from "./use-one-click-call";
import type { MonitorEvent } from "@/lib/live-monitor";
import type { ExecutionStep } from "@/lib/mcp-execution";
import { eventLabel, type WorkflowStage } from "./screen-a-evidence";
import { friendlyToolName, friendlyToolActivity } from "@/lib/avery-tool-labels";
import { ChatAppointmentOptions } from "./chat-appointment-options";

const STAGE_NAMES = [
  "Connect & Intake",
  "Verify",
  "Slot Search",
  "Confirm & Book",
  "Wrap-up",
] as const;

export function UnifiedWorkflowStepper({
  intake,
  scheduling,
  ended,
  events,
}: {
  intake: WorkflowStage[];
  scheduling: WorkflowStage[];
  ended: boolean;
  events: MonitorEvent[];
}) {
  const stageStates = [
    intake[0]?.state ?? "pending",
    scheduling[1]?.state ?? "pending",
    scheduling[2]?.state ?? "pending",
    scheduling[5]?.state ?? "pending",
    events.some((e) => e.event_type === "call_completed")
      ? "complete"
      : ended
        ? "active"
        : "pending",
  ];
  return (
    <nav
      aria-label="Unified scheduling workflow"
      className="rounded-xl border border-[#dfe1e2] bg-white px-3 py-3"
    >
      <ol className="grid grid-cols-5 gap-2">
        {STAGE_NAMES.map((name, index) => {
          const state = stageStates[index];
          return (
            <li key={name} className="min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={`grid size-7 shrink-0 place-items-center rounded-full border text-xs font-semibold ${state === "complete" ? "border-green-700 bg-green-700 text-white" : state === "active" ? "border-[#005ea2] bg-blue-50 text-[#005ea2]" : "border-slate-200 bg-slate-50 text-slate-600"}`}
                >
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold text-[#162e51] sm:text-xs">{name}</p>
                  <p className="text-[10px] text-slate-500">
                    {state === "complete"
                      ? "Verified step"
                      : state === "active"
                        ? "In progress"
                        : "Awaiting evidence"}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

type ConversationTab = "live" | "transcript" | "mcp";
function formatTime(ms: number) {
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
type FeedItem =
  | { kind: "dialogue"; id: string; time: number; line: LiveTranscriptLine }
  | { kind: "tool"; id: string; time: number; step: ExecutionStep }
  | { kind: "activity"; id: string; time: number; event: MonitorEvent };

function McpActivityCard({ step }: { step: ExecutionStep }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="rounded-lg border border-[#d9e8f6] bg-[#f7faff] px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Server className="size-4 text-[#005ea2]" aria-hidden="true" />
        <strong className="text-sm text-[#162e51]">{friendlyToolName(step.tool)}</strong>
        <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-[#005ea2]">
          {step.status === "succeeded"
            ? step.tool === "verify_synthetic_identity"
              ? "Verified"
              : "Complete"
            : step.status.replaceAll("_", " ")}
        </span>
        {step.durationMs !== undefined && step.durationMs > 0 && (
          <span className="text-xs text-slate-500">{step.durationMs} ms</span>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-600">
        MCP · <code>{step.tool}</code> · {friendlyToolActivity(step.tool)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {step.category === "dataset"
          ? "Access"
          : step.category === "write"
            ? "Write"
            : step.category === "read"
              ? "Read"
              : "MCP"}{" "}
        ·{" "}
        {step.invokedBy === "agent"
          ? "Avery via MCP · IBM agent selection verified"
          : "Selection origin not verified"}
      </p>
      <button
        type="button"
        className="mt-2 inline-flex min-h-9 items-center gap-1 text-xs font-medium text-[#005ea2] underline-offset-2 hover:underline"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <FileJson className="size-3.5" /> {expanded ? "Hide" : "Inspect"} execution evidence
        <ChevronDown className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>
      {expanded && (
        <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 break-all border-t pt-3 text-xs">
          <dt className="font-medium">Tool ID</dt>
          <dd className="font-mono">{step.tool}</dd>
          <dt className="font-medium">Source</dt>
          <dd>{step.source}</dd>
          <dt className="font-medium">Provenance</dt>
          <dd>{step.provenance}</dd>
          <dt className="font-medium">Correlation</dt>
          <dd className="font-mono">{step.correlationId ?? "Unavailable"}</dd>
          <dt className="font-medium">Call ID</dt>
          <dd className="font-mono">{step.toolCallId ?? "Unavailable"}</dd>
          <dt className="font-medium">Error code</dt>
          <dd>{step.errorCode ?? "None observed"}</dd>
          <dt className="font-medium">JSON-RPC</dt>
          <dd>
            Request and response payloads are not exposed by this sanitized observer. No JSON is
            synthesized.
          </dd>
        </dl>
      )}
    </article>
  );
}

export function LiveConversationFeed({
  agentPreparing = false,
  transcript,
  steps,
  events,
  callActive,
  observerError,
  observerPhase,
}: {
  agentPreparing?: boolean;
  transcript: LiveTranscriptLine[];
  steps: ExecutionStep[];
  events: MonitorEvent[];
  callActive: boolean;
  observerError: string;
  observerPhase: string;
}) {
  const [tab, setTab] = useState<ConversationTab>("live");
  const [showActivity, setShowActivity] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const content = useRef<HTMLOListElement>(null);
  const [paused, setPaused] = useState(false);
  const confirmed = events.filter((e) => e.voice_booking?.state === "BOOKED_SIMULATED").at(-1);
  const latestSlotEvent = events.filter((e) => e.appointment_options || e.voice_booking).at(-1);
  const selected =
    latestSlotEvent?.voice_booking?.state === "OFFERED" ? latestSlotEvent : undefined;
  const jumpToLatest = () => {
    followLatest.current = true;
    setPaused(false);
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  };
  useEffect(() => {
    if (callActive) {
      followLatest.current = true;
      setPaused(false);
    }
  }, [callActive]);
  useEffect(() => {
    if (!content.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followLatest.current && scroller.current)
        scroller.current.scrollTop = scroller.current.scrollHeight;
    });
    observer.observe(content.current);
    return () => observer.disconnect();
  }, []);
  const items = useMemo<FeedItem[]>(() => {
    const messages: FeedItem[] = transcript.map((line) => ({
      kind: "dialogue",
      id: `dialogue-${line.speaker}-${line.id}`,
      time: line.receivedAt,
      line,
    }));
    const toolEvents: FeedItem[] = steps.map((step) => ({
      kind: "tool",
      id: `tool-${step.id}`,
      time: Date.parse(step.startedAt) || 0,
      step,
    }));
    const other: FeedItem[] = events
      .filter(
        (event) => event.event_type !== "mcp_tool_called" && event.event_type !== "mcp_tool_result",
      )
      .map((event) => ({
        kind: "activity",
        id: `event-${event.event_id}`,
        time: Date.parse(event.occurred_at) || 0,
        event,
      }));
    return [...messages, ...toolEvents, ...other].sort(
      (a, b) => a.time - b.time || a.id.localeCompare(b.id),
    );
  }, [transcript, steps, events]);
  const visible = items
    .filter(
      (item) =>
        !(
          tab === "live" &&
          item.kind === "activity" &&
          (((confirmed || selected) && item.event.appointment_options) ||
            (item.event.voice_booking?.state === "OFFERED" &&
              item.event.event_id !== selected?.event_id))
        ),
    )
    .filter((item) =>
      tab === "transcript"
        ? item.kind === "dialogue"
        : tab === "mcp"
          ? item.kind !== "dialogue"
          : item.kind === "dialogue" ||
            (item.kind === "activity" &&
              Boolean(item.event.appointment_options || item.event.voice_booking)) ||
            showActivity,
    );
  useLayoutEffect(() => {
    if (followLatest.current && scroller.current) {
      scroller.current.scrollTop = scroller.current.scrollHeight;
    }
  }, [visible.length, transcript, steps, events, tab]);
  return (
    <section
      aria-label="Live Conversation"
      className="msa-workspace-conversation flex min-h-[420px] min-w-0 flex-col rounded-xl border border-[#dfe1e2] bg-white"
    >
      <div className="border-b px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#162e51]">Live Conversation</h2>
            <p className="text-xs text-slate-500">Dialogue · Agent activity · MCP evidence</p>
          </div>
          <label className="inline-flex items-center gap-2 text-xs text-[#005ea2]">
            <input
              type="checkbox"
              checked={showActivity}
              onChange={(e) => setShowActivity(e.target.checked)}
              className="size-4"
            />
            Show Agent Activity & MCP
          </label>
        </div>
        <div
          role="tablist"
          aria-label="Conversation views"
          className="mt-3 flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1"
        >
          {(
            [
              ["live", "Live Stream"],
              ["transcript", "Transcript Only"],
              ["mcp", "MCP & Telemetry"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => {
                setTab(value);
                followLatest.current = true;
              }}
              className={`min-h-9 flex-1 rounded-md px-2 text-xs font-semibold ${tab === value ? "bg-white text-[#005ea2] shadow-sm" : "text-slate-600"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div
        ref={scroller}
        role="tabpanel"
        tabIndex={0}
        aria-label={
          tab === "live"
            ? "Live dialogue and agent activity"
            : tab === "transcript"
              ? "LiveKit transcript"
              : "MCP telemetry"
        }
        className="msa-conversation-scroll min-h-[250px] flex-1 overflow-y-auto px-5 py-5 focus-visible:outline-2 focus-visible:outline-[#005ea2]"
        onScroll={(e) => {
          const target = e.currentTarget;
          followLatest.current = target.scrollHeight - target.scrollTop - target.clientHeight < 85;
          setPaused(!followLatest.current);
        }}
      >
        {visible.length === 0 && (
          <div
            role="status"
            className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center"
          >
            <Activity className="size-8 text-[#005ea2]" />
            <strong className="text-sm text-[#162e51]">
              {callActive
                ? "Awaiting observable conversation data"
                : "Conversation will appear here"}
            </strong>
            <p className="max-w-md text-xs text-slate-600">
              Only real LiveKit captions and authorized backend events appear. A connected voice
              call does not guarantee transcript access.
            </p>
          </div>
        )}
        <ol ref={content} aria-label="Time-ordered conversation items" className="space-y-5">
          {visible.map((item) => (
            <li key={item.id} className="min-w-0">
              {item.kind === "dialogue" ? (
                <article className="border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-2 text-xs">
                    <strong className="text-[#162e51]">{item.line.speaker}</strong>
                    <span className="text-slate-500">
                      {formatTime(item.time)} ·{" "}
                      {item.line.source === "typed"
                        ? "Typed reply"
                        : `${item.line.final ? "Final" : "Partial"} LiveKit caption`}
                    </span>
                  </div>
                  <p
                    className={`mt-2 whitespace-pre-wrap break-words text-sm leading-7 ${item.line.final ? "text-[#162e51]" : "text-slate-500"}`}
                  >
                    {item.line.text}
                  </p>
                </article>
              ) : item.kind === "tool" ? (
                <McpActivityCard step={item.step} />
              ) : item.event.source === "application" &&
                item.event.event_type === "voice_identity_verified" ? (
                <p className="rounded-lg border px-3 py-2 text-sm">
                  Voice service · Identity verified
                </p>
              ) : item.event.voice_booking &&
                (item.event.event_id === confirmed?.event_id ||
                  item.event.event_id === selected?.event_id) ? (
                <article
                  aria-label={
                    item.event.voice_booking.state === "OFFERED"
                      ? "Selected appointment"
                      : "Confirmed appointment"
                  }
                  className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-emerald-950"
                >
                  <h3 className="font-semibold">
                    {item.event.voice_booking.state === "OFFERED"
                      ? "Selected · awaiting confirmation"
                      : "Confirmed appointment"}
                  </h3>
                  {item.event.voice_booking.clinic_name && (
                    <p>{item.event.voice_booking.clinic_name}</p>
                  )}
                  {item.event.voice_booking.facility_name && (
                    <p>Demo facility: {item.event.voice_booking.facility_name}</p>
                  )}
                  {item.event.voice_booking.provider_name && (
                    <p>{item.event.voice_booking.provider_name}</p>
                  )}
                  <p>
                    Primary Care ·{" "}
                    {item.event.voice_booking.patient_time_zone
                      ? new Date(item.event.voice_booking.begins_at).toLocaleString("en-US", {
                          timeZone: item.event.voice_booking.patient_time_zone,
                          timeZoneName: "short",
                        })
                      : "Patient time zone not confirmed"}
                  </p>
                  {item.event.voice_booking.appointment_id && (
                    <p className="mt-2 break-all text-xs">
                      Confirmation: {item.event.voice_booking.appointment_id}
                    </p>
                  )}
                  {item.event.voice_booking.state === "BOOKED_SIMULATED" && (
                    <>
                      <p className="text-xs">Appointment saved and verified</p>
                      {item.event.voice_booking.crm_note_status === "SAVED" && (
                        <p className="text-xs">CRM note saved by the booking service</p>
                      )}
                    </>
                  )}
                </article>
              ) : item.event.appointment_options ? (
                <ChatAppointmentOptions
                  data={item.event.appointment_options}
                  current={
                    events.filter((e) => e.appointment_options || e.voice_booking).at(-1)
                      ?.event_id === item.event.event_id
                  }
                />
              ) : (
                <details className="border-l-2 border-[#b9d3e8] py-1 pl-3">
                  <summary className="cursor-pointer text-xs font-medium text-[#162e51]">
                    {eventLabel(item.event)}
                  </summary>
                  <p className="mt-1 text-xs text-slate-600">
                    Observed {item.event.source} · {item.event.status ?? "No outcome supplied"} ·{" "}
                    {item.event.occurred_at || "time unavailable"}
                  </p>
                </details>
              )}
            </li>
          ))}
        </ol>
        {agentPreparing && callActive && tab === "live" && showActivity && (
          <p role="status" className="py-2 text-xs text-slate-600">
            Avery is preparing a response�
          </p>
        )}
        {observerError && (
          <p role="status" className="mt-4 text-xs text-amber-800">
            Activity feed unavailable: {observerError}
          </p>
        )}
      </div>
      {paused && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="mx-auto my-2 min-h-10 rounded-full bg-[#005ea2] px-5 text-sm font-semibold text-white"
        >
          Jump to latest
        </button>
      )}
      <div className="flex flex-wrap justify-between gap-2 border-t bg-slate-50 px-4 py-2 text-[11px] text-slate-500">
        <span>
          Observer: {observerPhase} · {events.length} events · {steps.length} tool calls
        </span>
        <span>
          <Clock3 className="mr-1 inline size-3" /> Payload details are redacted by the backend
        </span>
      </div>
    </section>
  );
}

export function SchedulingEncounterSummary({
  identityVerified,
  caseId,
  bookingProof = null,
  appointmentOptions = null,
}: {
  identityVerified: boolean;
  caseId: string | null;
  bookingProof?: import("@/lib/voice-booking-proof").VoiceBookingProof | null;
  appointmentOptions?: import("@/lib/voice-appointment-options").VoiceAppointmentOptions | null;
}) {
  const clinics = new Set(appointmentOptions?.options.map((o) => o.facility_name ?? o.clinic_name));
  const offeredClinic = clinics.size === 1 ? [...clinics][0] : null;
  const clinic =
    bookingProof?.facility_name ??
    bookingProof?.clinic_name ??
    (bookingProof?.state !== "BOOKED_SIMULATED" ? offeredClinic : null);
  return (
    <section
      aria-label="Scheduling Encounter"
      className="msa-workspace-scheduling h-full rounded-xl border border-[#dfe1e2] bg-white p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <h2 className="text-lg font-semibold text-[#162e51]">Scheduling Encounter</h2>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs">
          {identityVerified ? "Identity verified" : "Awaiting verification"}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        {[
          [
            "Care Type",
            bookingProof || appointmentOptions ? "Primary Care · Synthetic" : "Awaiting intake",
          ],
          ["Facility / Clinic", clinic || "Not resolved"],
          [
            "Selected Slot",
            bookingProof?.patient_time_zone
              ? new Date(bookingProof.begins_at).toLocaleString("en-US", {
                  timeZone: bookingProof.patient_time_zone,
                  timeZoneName: "short",
                })
              : bookingProof
                ? "Patient time zone not confirmed"
                : "No verified selection",
          ],
          [
            "Booking Status",
            bookingProof?.state === "BOOKED_SIMULATED"
              ? "Booked · independent readback verified"
              : bookingProof
                ? "Offered · awaiting explicit consent"
                : "Not confirmed",
          ],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 rounded-lg border bg-slate-50 p-3">
            <dt className="text-[10px] uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="mt-1 break-words font-semibold text-[#162e51]">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[#162e51]">
          <CalendarDays className="size-4 text-[#005ea2]" />{" "}
          {bookingProof?.state === "BOOKED_SIMULATED"
            ? "Confirmed Appointment"
            : "Available Appointments"}
        </h3>
        <p className="mt-3 rounded-md border border-dashed px-3 py-5 text-center text-xs text-slate-600">
          {bookingProof
            ? bookingProof.state === "BOOKED_SIMULATED"
              ? `Synthetic confirmation: ${bookingProof.appointment_id}. This is not a real VA appointment.`
              : "Avery has verified this synthetic appointment option. Confirm or decline it verbally during your call."
            : "No verified case-scoped appointment inventory is available through the current sanitized event feed. No slot is selectable or bookable here yet."}
        </p>
      </div>
      {caseId && (
        <p className="mt-3 break-all text-[10px] text-slate-500">Synthetic case: {caseId}</p>
      )}
    </section>
  );
}
