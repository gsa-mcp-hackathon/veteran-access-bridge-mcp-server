import { describe, expect, it } from "vitest";
import {
  DEMO_MSA,
  OTHER_MSA,
  handoffReducer,
  initialHandoff,
  needsAttention,
  ownershipLabel,
  type HandoffScenario,
} from "@/lib/handoff";
function pending(scenario: HandoffScenario = "mismatch") {
  let state = initialHandoff(scenario);
  for (let i = 0; i < 5; i++) state = handoffReducer(state, { type: "advance" });
  return state;
}
describe("Synthetic handoff boundaries", () => {
  it("mismatch creates requested then pending without an owner", () => {
    let state = initialHandoff("mismatch");
    for (let i = 0; i < 4; i++) state = handoffReducer(state, { type: "advance" });
    expect(state.verification).toBe("mismatched");
    expect(state.ownership).toBe("requested");
    state = handoffReducer(state, { type: "advance" });
    expect(state.ownership).toBe("pending");
    expect(state.owner).toBeUndefined();
    expect(needsAttention(state)).toBe(true);
  });
  it("acceptance is not media join or identity matching", () => {
    const accepted = handoffReducer(pending(), { type: "accept" });
    expect(accepted.owner).toBe(DEMO_MSA);
    expect(accepted.joined).toBe(false);
    expect(accepted.verification).toBe("mismatched");
    expect(ownershipLabel(accepted)).toBe("Accepted · awaiting media join");
    const joined = handoffReducer(accepted, { type: "join" });
    expect(joined.joined).toBe(true);
    expect(joined.ownership).toBe("human");
    expect(needsAttention(joined)).toBe(false);
  });
  it("reject requires reason and route", () => {
    const state = pending();
    expect(
      handoffReducer(state, { type: "reject", reason: " ", fallback: "Supervisor" }).ownership,
    ).toBe("pending");
    expect(
      handoffReducer(state, { type: "reject", reason: "Unavailable", fallback: "" }).ownership,
    ).toBe("pending");
    const rejected = handoffReducer(state, {
      type: "reject",
      reason: "Unavailable",
      fallback: "Supervisor verification queue",
    });
    expect(rejected.ownership).toBe("rejected");
    expect(rejected.fallback).toBe("Supervisor verification queue");
    expect(needsAttention(rejected)).toBe(true);
  });
  it("timeout retains unresolved request with fallback", () => {
    const state = handoffReducer(pending("timeout"), { type: "advance" });
    expect(state.ownership).toBe("timeout");
    expect(state.owner).toBeUndefined();
    expect(state.fallback).toBe("Supervisor verification queue");
    expect(needsAttention(state)).toBe(true);
  });
  it("disconnect retains queue request and blocks acceptance and join", () => {
    const state = handoffReducer(pending(), { type: "disconnect" });
    expect(state.requestId).toBe("SYN-HO-mismatch");
    expect(state.media).toBe("disconnected");
    expect(needsAttention(state)).toBe(true);
    expect(handoffReducer(state, { type: "accept" }).owner).toBeUndefined();
    expect(handoffReducer(state, { type: "join" }).joined).toBe(false);
  });
  it("reconnect preserves accepted owner but requires another joined fixture", () => {
    const joined = handoffReducer(handoffReducer(pending(), { type: "accept" }), { type: "join" });
    const reconnect = handoffReducer(handoffReducer(joined, { type: "disconnect" }), {
      type: "reconnect",
    });
    expect(reconnect.owner).toBe(DEMO_MSA);
    expect(reconnect.ownership).toBe("accepted");
    expect(reconnect.joined).toBe(false);
  });
  it("duplicate accept is idempotent and race cannot create second owner", () => {
    const accepted = handoffReducer(pending(), { type: "accept" });
    const duplicate = handoffReducer(accepted, { type: "accept" });
    expect(duplicate.audit.length).toBe(accepted.audit.length);
    expect(duplicate.owner).toBe(DEMO_MSA);
    const race = handoffReducer(pending("race"), { type: "advance" });
    expect(handoffReducer(race, { type: "accept" }).owner).toBe(OTHER_MSA);
    expect(handoffReducer(race, { type: "join" }).joined).toBe(false);
  });
  it("end clears human media badge; close requires outcome and retains audit", () => {
    const human = handoffReducer(handoffReducer(pending(), { type: "accept" }), { type: "join" });
    const ended = handoffReducer(human, { type: "end" });
    expect(ended.media).toBe("ended");
    expect(ended.joined).toBe(false);
    expect(ended.ownership).toBe("accepted");
    expect(handoffReducer(ended, { type: "close", outcome: "" }).ownership).toBe("accepted");
    const closed = handoffReducer(ended, { type: "close", outcome: "Callback review queued" });
    expect(closed.ownership).toBe("closed");
    expect(needsAttention(closed)).toBe(false);
    expect(handoffReducer(closed, { type: "accept" }).audit).toEqual(closed.audit);
  });
});

describe("Terminal fallback recovery", () => {
  it("ended requested can close through fallback without advancing to pending or claiming an owner", () => {
    let state = initialHandoff("mismatch");
    for (let i = 0; i < 4; i++) state = handoffReducer(state, { type: "advance" });
    state = handoffReducer(state, { type: "end" });
    state = handoffReducer(state, { type: "fallback", route: "Safe callback review queue" });
    const closed = handoffReducer(state, {
      type: "close",
      outcome: "Caller disconnected; safe callback review queued",
    });
    expect(closed.ownership).toBe("closed");
    expect(closed.owner).toBeUndefined();
    expect(closed.verification).toBe("mismatched");
    expect(closed.audit.some((event) => event.event === "handoff.accepted")).toBe(false);
  });
  it.each(["end", "disconnect"] as const)(
    "%s pending closes only after confirmed fallback and required resolution",
    (type) => {
      const stopped = handoffReducer(pending(), { type });
      expect(
        handoffReducer(stopped, {
          type: "close",
          outcome: "Caller disconnected; safe callback review queued",
        }).ownership,
      ).toBe("pending");
      const routed = handoffReducer(stopped, {
        type: "fallback",
        route: "Safe callback review queue",
      });
      expect(handoffReducer(routed, { type: "close", outcome: " " }).ownership).toBe("pending");
      const closed = handoffReducer(routed, {
        type: "close",
        outcome: "Caller disconnected; safe callback review queued",
      });
      expect(closed.ownership).toBe("closed");
      expect(closed.owner).toBeUndefined();
      expect(closed.joined).toBe(false);
      expect(closed.verification).toBe("mismatched");
      expect(closed.media).toBe("ended");
      expect(needsAttention(closed)).toBe(false);
      expect(closed.audit.slice(-2).map((e) => e.event)).toEqual([
        "handoff.fallback_routed",
        "handoff.closed",
      ]);
      expect(handoffReducer(closed, { type: "close", outcome: "Repeat" }).audit).toEqual(
        closed.audit,
      );
      expect(
        handoffReducer(routed, { type: "fallback", route: "Safe callback review queue" }).audit,
      ).toEqual(routed.audit);
    },
  );
  it("active pending cannot close through fallback, and reconnect restores active acceptance prerequisites", () => {
    const active = handoffReducer(pending(), {
      type: "fallback",
      route: "Safe callback review queue",
    });
    expect(
      handoffReducer(active, { type: "close", outcome: "Verification routed to supervisor" })
        .ownership,
    ).toBe("pending");
    const disconnected = handoffReducer(pending(), { type: "disconnect" });
    expect(handoffReducer(disconnected, { type: "accept" }).owner).toBeUndefined();
    const routed = handoffReducer(disconnected, {
      type: "fallback",
      route: "Safe callback review queue",
    });
    const reconnected = handoffReducer(routed, { type: "reconnect" });
    expect(reconnected.terminalFallback).toBe(false);
    expect(
      handoffReducer(reconnected, { type: "close", outcome: "Verification routed to supervisor" })
        .ownership,
    ).toBe("pending");
  });
  it("historical joined event retains its original identity and time across media loss", () => {
    const joined = handoffReducer(handoffReducer(pending(), { type: "accept" }), { type: "join" });
    const event = joined.audit.find((e) => e.event === "handoff.joined");
    const recovered = handoffReducer(handoffReducer(joined, { type: "disconnect" }), {
      type: "reconnect",
    });
    expect(recovered.joined).toBe(false);
    expect(recovered.audit.find((e) => e.event === "handoff.joined")).toEqual(event);
  });
});
