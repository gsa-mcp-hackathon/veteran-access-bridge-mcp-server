import { act, renderHook, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLive } from "@/components/msa/use-live";
import {
  canReviewAppointment,
  emptyEncounter,
  scriptFor,
  slotsFor,
  type Encounter,
} from "@/lib/scenario";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const ready = (): Encounter => ({
  ...emptyEncounter(),
  verified: true,
  slotsLoaded: true,
  evaluated: true,
  selectedId: "s1",
  verifiedSlot: true,
  veteranConfirmed: true,
  awaitingApproval: true,
});
async function finishReplay(kind: "success" | "verification-review" | "exception-approval") {
  for (let i = 0; i < scriptFor(kind).length; i++)
    await act(async () => {
      vi.advanceTimersByTime(1800);
    });
}
describe("Phase 1 synthetic boundaries", () => {
  it("morning preference ranks rather than excluding 13:00 and 15:30 slots", () => {
    const slots = slotsFor({
      ...ready(),
      selectedId: undefined,
      prefs: ["Mornings (before 12:00)"],
    });
    expect(slots.find((slot) => slot.time === "13:00")?.status).toBe("eligible");
    expect(slots.find((slot) => slot.time === "15:30")?.status).toBe("eligible");
    expect(slots.filter((slot) => slot.status === "excluded").map((slot) => slot.id)).toEqual([
      "s3",
      "s7",
    ]);
  });
  it("unsuccessful identity verification locks scheduling availability", () => {
    expect(slotsFor({ ...ready(), verified: false })).toEqual([]);
    expect(canReviewAppointment({ ...ready(), verified: false })).toBe(false);
  });
  it.each(["evaluated", "verifiedSlot", "veteranConfirmed", "awaitingApproval"] as const)(
    "approval requires %s",
    (field) => {
      expect(canReviewAppointment({ ...ready(), [field]: false })).toBe(false);
      expect(canReviewAppointment(ready())).toBe(true);
    },
  );
  it("books routine verified primary care autonomously and resets session controls", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useLive());
    act(() => result.current.approve());
    expect(result.current.enc.booked).toBe(false);
    await finishReplay("success");
    expect(result.current.playing).toBe(false);
    expect(result.current.enc.awaitingApproval).toBe(false);
    expect(result.current.enc.booked).toBe(true);
    act(() => result.current.approve());
    expect(result.current.enc.booked).toBe(true);
    act(() => {
      result.current.setMuted(true);
      result.current.setJoined(true);
    });
    act(() => result.current.reset());
    expect(result.current.enc).toEqual(emptyEncounter());
    expect(result.current.messages).toEqual([]);
    expect(result.current.events).toEqual([]);
    expect(result.current.muted).toBe(false);
    expect(result.current.joined).toBe(false);
  });
  it("review candidate never verifies identity or enables booking", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useLive("verification-review"));
    await finishReplay("verification-review");
    expect(result.current.voice).toBe("awaiting");
    expect(result.current.enc.verified).toBe(false);
    expect(result.current.slots).toEqual([]);
    act(() => result.current.approve());
    expect(result.current.enc.booked).toBe(false);
  });
  it("decline returns to Select with cleared proposal; end prevents approval", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useLive("exception-approval"));
    await finishReplay("exception-approval");
    act(() => result.current.decline("Clinical review required"));
    expect(result.current.stage).toBe("Select");
    expect(result.current.enc.selectedId).toBeUndefined();
    expect(result.current.enc.verifiedSlot).toBe(false);
    expect(result.current.enc.veteranConfirmed).toBe(false);
    expect(result.current.enc.declineReason).toBe("Clinical review required");
    act(() => result.current.reset());
    await finishReplay("exception-approval");
    act(() => result.current.end());
    act(() => result.current.approve());
    expect(result.current.voice).toBe("disconnected");
    expect(result.current.enc.awaitingApproval).toBe(false);
    expect(result.current.enc.booked).toBe(false);
  });
});
