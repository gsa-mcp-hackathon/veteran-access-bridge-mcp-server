import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MSAAppShell } from "@/components/msa/app-shell";
import { scriptFor } from "@/lib/scenario";
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
  ClientOnly: ({ fallback }: { fallback: React.ReactNode }) => <>{fallback}</>,
}));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn();
});
it.each([390, 768, 1440])("Live Conversation and inspector are available at %ipx", (width) => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  render(<MSAAppShell />);
  expect(screen.getAllByRole("region", { name: "Live Conversation" }).length).toBe(1);
  expect(screen.getByRole("region", { name: "MCP Execution Inspector" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Scheduling encounter" })).toBeInTheDocument();
});
it("autonomous success remains complete when switching to a handoff and back", async () => {
  vi.useFakeTimers();
  render(<MSAAppShell />);
  fireEvent.click(screen.getByText("Advanced · developer scripted replay (not live)"));
  fireEvent.click(screen.getByRole("button", { name: "Start scripted replay (demo only)" }));
  for (let i = 0; i < scriptFor("success").length; i++)
    await act(async () => {
      vi.advanceTimersByTime(1800);
    });
  expect(
    screen.getByRole("heading", { name: "Appointment Booked · Simulated" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Synthetic scenario replay"), {
    target: { value: "mismatch" },
  });
  expect(screen.queryByRole("region", { name: "Scheduling encounter" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Avery's work" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Synthetic scenario replay"), {
    target: { value: "success" },
  });
  expect(
    screen.getByRole("heading", { name: "Appointment Booked · Simulated" }),
  ).toBeInTheDocument();
});
it("routine path has no MSA approval, call controls, or private MSA chat", () => {
  render(<MSAAppShell />);
  expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  for (const name of [/^Join/, /^Mute/, /^Hold/, /^End/, /^Monitor/])
    expect(screen.queryByRole("button", { name })).toBeNull();
  expect(screen.queryByText(/Chat with Avery/)).toBeNull();
  expect(screen.queryByPlaceholderText(/Type a message/i)).toBeNull();
  expect(screen.getByText(/SANDBOX · Live observer · LiveKit not connected/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Not connected/ })).toBeInTheDocument();
});
it("shows no fabricated booking or MSA handoff before a real observer connects", () => {
  render(<MSAAppShell />);
  expect(screen.getByRole("region", { name: "Scheduling encounter" })).toHaveTextContent(
    "Awaiting authoritative evidence",
  );
  expect(screen.queryByText("Identity prerequisite not met")).toBeNull();
  expect(screen.queryByRole("button", { name: "Handoff inbox" })).toBeNull();
  expect(screen.queryByText("Waiting for verification")).toBeNull();
});
