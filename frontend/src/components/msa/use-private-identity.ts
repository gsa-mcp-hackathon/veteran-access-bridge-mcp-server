import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { Room } from "livekit-client";

/** Private addressed RPC; never call the typed-reply or transcript paths. */
export async function identityRequest(r: Room, digits?: string): Promise<boolean> {
  if (digits !== undefined && !/^[0-9]{4}$/.test(digits)) throw new Error("Invalid input");
  const { ParticipantKind } = await import("livekit-client");
  const agents = [...r.remoteParticipants.values()].filter((p) => p.kind === ParticipantKind.AGENT);
  if (agents.length !== 1) throw new Error("Avery is unavailable");
  const raw = await r.localParticipant.performRpc({
    destinationIdentity: agents[0]!.identity,
    method: "vab.private-identity",
    payload: JSON.stringify(
      digits === undefined ? { action: "status" } : { action: "submit", digits },
    ),
    responseTimeout: digits === undefined ? 5000 : 30000,
  });
  if (raw.length > 64) throw new Error("Invalid verification state");
  const state: unknown = JSON.parse(raw);
  if (
    !state ||
    typeof state !== "object" ||
    !("required" in state) ||
    typeof state.required !== "boolean"
  )
    throw new Error("Invalid verification state");
  return state.required;
}

export function usePrivateIdentity(
  room: RefObject<Room | null>,
  phase: string,
  setMuted: (value: boolean) => void,
) {
  const [required, setRequired] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const generation = useRef(0);
  const restoreMic = useRef(false);
  const privateRoom = useRef<Room | null>(null);

  const apply = useCallback(
    async (r: Room, needed: boolean) => {
      if (room.current !== r) return;
      if (needed) {
        setRequired(true);
        if (privateRoom.current !== r) {
          restoreMic.current = r.localParticipant.isMicrophoneEnabled;
          privateRoom.current = r;
        }
        await r.localParticipant.setMicrophoneEnabled(false);
        if (room.current !== r) return;
        setMuted(true);
        setReady(true);
      } else {
        if (privateRoom.current === r && restoreMic.current) {
          await r.localParticipant.setMicrophoneEnabled(true);
          if (room.current !== r) return;
          setMuted(false);
        }
        privateRoom.current = null;
        restoreMic.current = false;
        setRequired(false);
        setReady(false);
      }
    },
    [room, setMuted],
  );

  useEffect(() => {
    if (phase !== "live") {
      setRequired(false);
      setReady(false);
      setError("");
      privateRoom.current = null;
      restoreMic.current = false;
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const r = room.current;
      if (!stopped && r && !busy.current) {
        const version = generation.current;
        try {
          const needed = await identityRequest(r);
          if (!stopped && !busy.current && version === generation.current) await apply(r, needed);
        } catch {
          // No digits or remote exception messages enter UI logs.
        }
      }
      if (!stopped) timer = setTimeout(() => void poll(), 1500);
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [phase, room, apply]);

  const submit = useCallback(
    async (digits: string) => {
      const r = room.current;
      if (!r || !required || !ready || busy.current || !/^[0-9]{4}$/.test(digits)) return false;
      busy.current = true;
      generation.current += 1;
      setError("");
      try {
        const needed = await identityRequest(r, digits);
        await apply(r, needed);
        return true;
      } catch {
        setError("Verification was not completed. Wait for Avery, then try again if asked.");
        return false;
      } finally {
        busy.current = false;
      }
    },
    [room, required, ready, apply],
  );

  return { required, ready, error, submit };
}
