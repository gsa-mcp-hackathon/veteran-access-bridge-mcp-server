import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SafeHandoffContext } from "@/components/msa/handoff-panels";
import { handoffReducer, initialHandoff } from "@/lib/handoff";
afterEach(cleanup);
it("mismatch never exposes protected availability or appointment actions, even after accept/join", () => {
  let state = initialHandoff("mismatch");
  for (let i = 0; i < 5; i++) state = handoffReducer(state, { type: "advance" });
  state = handoffReducer(handoffReducer(state, { type: "accept" }), { type: "join" });
  render(<SafeHandoffContext state={state} onReview={() => {}} />);
  expect(screen.queryByRole("button", { name: "Review & approve" })).toBeNull();
  expect(screen.queryByRole("button", { name: /08:30/ })).toBeNull();
  expect(screen.queryByText(/Dr\. A\. Ramirez/)).toBeNull();
  expect(screen.queryByRole("tab", { name: "Week" })).toBeNull();
  expect(state.verification).toBe("mismatched");
});
it("terminal fallback closure does not expose private scheduling or change mismatched verification", () => {
  let state = initialHandoff("mismatch");
  for (let i = 0; i < 5; i++) state = handoffReducer(state, { type: "advance" });
  state = handoffReducer(state, { type: "disconnect" });
  state = handoffReducer(state, { type: "fallback", route: "Safe callback review queue" });
  state = handoffReducer(state, {
    type: "close",
    outcome: "Caller disconnected; safe callback review queued",
  });
  render(<SafeHandoffContext state={state} onReview={() => {}} />);
  expect(state.verification).toBe("mismatched");
  expect(screen.queryByRole("button", { name: "Review & approve" })).toBeNull();
  expect(screen.queryByRole("button", { name: /08:30/ })).toBeNull();
  expect(screen.queryByText(/Dr\. A\. Ramirez/)).toBeNull();
});
