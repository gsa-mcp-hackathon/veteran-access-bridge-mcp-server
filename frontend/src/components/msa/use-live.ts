import { useEffect, useMemo, useState } from "react";
import {
  scriptFor,
  emptyEncounter,
  slotsFor,
  canReviewAppointment,
  canBookRoutine,
  type DemoCase,
  type ActivityEvent,
  type Encounter,
  type Message,
  type Slot,
  type Stage,
  type VoiceState,
} from "@/lib/scenario";
/* ---------------- scenario engine (replays synthetic backend events) ---------------- */
export interface Live {
  voice: VoiceState;
  stage: Stage;
  messages: Message[];
  events: ActivityEvent[];
  enc: Encounter;
  slots: Slot[];
  playing: boolean;
  muted: boolean;
  joined: boolean;
  setPlaying: (b: boolean) => void;
  reset: () => void;
  setMuted: (b: boolean) => void;
  setJoined: (b: boolean) => void;
  approve: () => void;
  decline: (reason: string) => void;
  end: () => void;
}

export function useLive(demoCase: DemoCase = "success", replayEnabled = true): Live {
  const script = scriptFor(demoCase);
  const [n, setN] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [muted, setMuted] = useState(false);
  const [joined, setJoined] = useState(false);
  const [extra, setExtra] = useState<{
    ev: ActivityEvent[];
    msg: Message[];
    enc: Partial<Encounter>;
    voice?: VoiceState;
    stage?: Stage;
  }>({ ev: [], msg: [], enc: {} });

  useEffect(() => {
    if (!replayEnabled || !playing || n >= script.length) return;
    const t = setTimeout(() => setN((x) => x + 1), script[n]?.kind === "update" ? 900 : 1700);
    return () => clearTimeout(t);
  }, [n, playing, replayEnabled, script]);

  const base = useMemo(() => {
    let voice: VoiceState = "listening";
    let stage: Stage = "Request";
    const messages: Message[] = [];
    const events: ActivityEvent[] = [];
    let enc = emptyEncounter();
    for (const s of script.slice(0, n)) {
      if (s.kind === "msg") {
        messages.push(s.msg);
        voice = s.voice;
      } else if (s.kind === "event") {
        events.push({ ...s.ev });
        voice = s.voice;
        if (s.stage) stage = s.stage;
        if (s.patch && (!s.patch.booked || canBookRoutine(enc))) enc = { ...enc, ...s.patch };
      } else {
        const e = events.find((x) => x.id === s.id);
        if (e) e.status = s.status;
        if (s.voice) voice = s.voice;
        if (s.stage) stage = s.stage;
        if (s.patch) enc = { ...enc, ...s.patch };
      }
    }
    return { voice, stage, messages, events, enc };
  }, [n, script]);

  const enc = { ...base.enc, ...extra.enc };
  const now = () => new Date().toTimeString().slice(0, 8);
  return {
    voice: extra.voice ?? base.voice,
    stage: extra.stage ?? base.stage,
    messages: [...base.messages, ...extra.msg],
    events: [
      ...base.events.map((e) =>
        e.status === "human" && extra.ev.length ? { ...e, status: "completed" as const } : e,
      ),
      ...extra.ev,
    ],
    enc,
    slots: slotsFor(enc),
    playing: replayEnabled && playing && n < script.length && extra.voice !== "disconnected",
    muted,
    joined,
    setPlaying,
    setMuted,
    setJoined,
    reset: () => {
      setN(0);
      setExtra({ ev: [], msg: [], enc: {} });
      setJoined(false);
      setMuted(false);
      setPlaying(true);
    },
    approve: () => {
      if (!canReviewAppointment(enc) || extra.voice === "disconnected") return;
      setExtra({
        enc: { awaitingApproval: false, approval: "approved", booked: true },
        voice: "speaking",
        stage: "Simulated Book",
        ev: [
          { id: "x1", label: "MSA approval recorded", status: "completed", time: now() },
          {
            id: "x2",
            label: "Simulated booking completed",
            status: "completed",
            time: now(),
            mcp: {
              tool: "scheduling.simulate_book",
              durationMs: 402,
              params: { slot: "PC-GREEN/2026-11-10T08:30", approved_by: "MSA W. Green" },
              result: "SIMULATED booking ref SIM-20261110-0830. No VistA write performed.",
              provenance: "Scheduling Engine · simulation mode",
              correlationId: "vab-7f3a-0006",
            },
          },
        ],
        msg: [
          {
            id: "x3",
            speaker: "avery",
            time: now(),
            text: "Synthetic booking complete: Tuesday, November 10th at 8:30 AM with Dr. Ramirez. No appointment or reminder was created in a live system.",
          },
        ],
      });
    },
    decline: (reason) => {
      if (!canReviewAppointment(enc) || extra.voice === "disconnected") return;
      setExtra({
        enc: {
          booked: false,
          awaitingApproval: false,
          approval: "declined",
          declineReason: reason,
          veteranConfirmed: false,
          verifiedSlot: false,
          selectedId: undefined,
        },
        voice: "processing",
        stage: "Select",
        ev: [{ id: "x1", label: `MSA declined — ${reason}`, status: "failed", time: now() }],
        msg: [
          {
            id: "x3",
            speaker: "avery",
            time: now(),
            text: "Synthetic proposal declined. Replay is paused at Select; restart to explore the appointment flow again.",
          },
        ],
      });
    },
    end: () => {
      setPlaying(false);
      setJoined(false);
      setExtra((e) => ({
        ...e,
        enc: { ...e.enc, awaitingApproval: false },
        voice: "disconnected",
      }));
    },
  };
}
