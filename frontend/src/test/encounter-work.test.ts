import { describe, expect, it } from "vitest";
import { artifactState, canSaveArtifact, copilotAnswer } from "@/lib/encounter-work";
import { canBookRoutine, emptyEncounter, type Encounter, type ActivityEvent } from "@/lib/scenario";
const ready = (): Encounter => ({
  ...emptyEncounter(),
  verified: true,
  slotsLoaded: true,
  evaluated: true,
  selectedId: "s1",
  verifiedSlot: true,
  veteranConfirmed: true,
});
const event = (id: string): ActivityEvent => ({
  id,
  label: id,
  status: "completed",
  time: "13:42:14",
});
describe("Routine booking prerequisites", () => {
  it.each(["verified", "slotsLoaded", "evaluated", "verifiedSlot", "veteranConfirmed"] as const)(
    "requires %s",
    (field) => {
      expect(canBookRoutine({ ...ready(), [field]: false })).toBe(false);
      expect(canBookRoutine(ready())).toBe(true);
    },
  );
  it("never auto-books an exception awaiting authorization or an excluded option", () => {
    expect(canBookRoutine({ ...ready(), awaitingApproval: true })).toBe(false);
    expect(canBookRoutine({ ...ready(), selectedId: "s3" })).toBe(false);
    expect(canBookRoutine({ ...ready(), selectedId: "unauthorized-consult" })).toBe(false);
  });
});
describe("Independent per-encounter work", () => {
  it("letter cannot generate before booking, even with a stray ready event", () => {
    expect(artifactState("letter", { enc: ready(), events: [event("work-letter-ready")] })).toBe(
      "Waiting",
    );
  });
  it("note and summary draft during call while letter and notification wait", () => {
    const live = { enc: { ...ready(), careCategory: "Primary Care" }, events: [] };
    expect(artifactState("note", live)).toBe("Draft");
    expect(artifactState("summary", live)).toBe("Draft");
    expect(artifactState("letter", live)).toBe("Waiting");
    expect(artifactState("notification", live)).toBe("Waiting");
    expect(canSaveArtifact("Draft")).toBe(false);
  });
  it("generation, local saving, finalization, recording and delivery remain distinct", () => {
    const live = {
      enc: { ...ready(), booked: true, careCategory: "Primary Care" },
      events: [event("work-letter-generating")],
    };
    expect(artifactState("letter", live)).toBe("Generating");
    live.events.push(event("work-letter-ready"));
    expect(artifactState("letter", live)).toBe("Generated");
    expect(artifactState("letter", live, true)).toBe("Saved locally");
    expect(artifactState("note", live)).toBe("Draft");
    live.events.push(event("work-note-final"), event("work-notification-queued"));
    expect(artifactState("note", live)).toBe("Finalized");
    expect(artifactState("note", live, true)).toBe("Recorded locally");
    expect(artifactState("summary", live)).toBe("Draft");
    expect(artifactState("notification", live)).toBe("Queued");
    expect(artifactState("notification", live, true)).toBe("Delivered (simulation)");
  });
  it("mismatch blocks every artifact and staff answers disclose no protected options", () => {
    const live = {
      enc: { ...ready(), verified: false, booked: true },
      events: [event("work-letter-ready")],
    };
    for (const id of ["letter", "note", "summary", "notification"] as const)
      expect(artifactState(id, live, true)).toBe("Blocked");
    expect(copilotAnswer("appointment", live, true)).not.toContain("08:30");
    expect(copilotAnswer("appointment", live, true)).toContain("No booking is permitted");
  });
});
