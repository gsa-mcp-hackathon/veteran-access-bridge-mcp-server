import { describe, expect, it, vi } from "vitest";
import { createLatencyProbe } from "@/lib/latency-probe";

describe("decoded audio diagnostics", () => {
  const id = "a".repeat(32);
  it("measures local silence-to-energy after the ready marker once", () => {
    const emit = vi.fn();
    const probe = createLatencyProbe(emit);
    probe.sample(0, 1);
    probe.ready(id, 10);
    probe.sample(0, 20);
    probe.sample(0.02, 130);
    probe.sample(0.04, 160);
    expect(emit).toHaveBeenCalledExactlyOnceWith({
      trace_id: id,
      ready_to_decoded_audio_ms: 120,
      status: "detected",
    });
  });
  it("rejects identifiers and reports overlap without fabricating latency", () => {
    const emit = vi.fn();
    const probe = createLatencyProbe(emit);
    probe.ready("patient-name", 1);
    expect(emit).not.toHaveBeenCalled();
    probe.sample(0.1, 2);
    probe.ready(id, 3);
    expect(emit).toHaveBeenLastCalledWith({
      trace_id: id,
      ready_to_decoded_audio_ms: null,
      status: "overlap",
    });
  });
  it("handles unavailable audio, timeout and cleanup", () => {
    const emit = vi.fn();
    const probe = createLatencyProbe(emit);
    probe.ready(id, 0);
    expect(emit.mock.lastCall?.[0].status).toBe("unavailable");
    probe.sample(0, 10);
    probe.ready(id, 11);
    probe.sample(0, 6000);
    expect(emit.mock.lastCall?.[0].status).toBe("timeout");
    probe.ready(id, 7000);
    probe.reset();
    probe.sample(0.1, 7100);
    expect(emit).toHaveBeenCalledTimes(2);
  });
});
