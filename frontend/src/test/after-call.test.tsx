import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { projectAfterCall } from "@/lib/after-call";
import { AfterCallCard } from "@/components/msa/after-call-card";

afterEach(cleanup);
const saved = {
  status: "COMPLETE",
  persisted: true,
  summary: "Confirmed appointment.",
  record_id: "11111111-1111-4111-8111-111111111111",
  letter: { text: "Appointment at 9 AM CST. Not sent.", delivery_status: "NOT_SENT" },
};

it("shows the saved CRM receipt and downloadable letter only from a complete result", () => {
  render(<AfterCallCard result={projectAfterCall(saved)} retry={() => {}} />);
  expect(screen.getByText("Wrap-up complete")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download appointment letter" })).toHaveAttribute(
    "download",
    "appointment-confirmation.txt",
  );
  expect(screen.getByText("Generated · Not sent")).toBeInTheDocument();
});

it("never projects pending records or forged delivery claims as completed", () => {
  expect(projectAfterCall({ ...saved, persisted: false })).toBeNull();
  expect(
    projectAfterCall({ ...saved, letter: { ...saved.letter, delivery_status: "SENT" } }),
  ).toBeNull();
  const pending = projectAfterCall({ ...saved, status: "PENDING" });
  render(<AfterCallCard result={pending} retry={() => {}} />);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByText("Wrap-up complete")).not.toBeInTheDocument();
});

it("does not create a letter for an unverified caller", () => {
  render(
    <AfterCallCard
      result={projectAfterCall({ status: "NOT_SAVED_UNVERIFIED" })}
      retry={() => {}}
    />,
  );
  expect(screen.getByText(/No patient CRM note/)).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
