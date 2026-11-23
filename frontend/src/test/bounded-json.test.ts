import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GATEWAY_BODY_TIMEOUT_MS,
  MAX_GATEWAY_BODY_BYTES,
  readBoundedJson,
} from "@/lib/bounded-json";

const request = (body: string, headers: Record<string, string> = {}) =>
  new Request("https://example.test/api/demo-call", { method: "POST", body, headers });
afterEach(() => vi.useRealTimers());

describe("bounded gateway JSON", () => {
  it("accepts ordinary requests and the exact byte boundary", async () => {
    expect(await readBoundedJson(request('{"action":"start"}'))).toEqual({ action: "start" });
    expect(
      await readBoundedJson(request('"' + "a".repeat(MAX_GATEWAY_BODY_BYTES - 2) + '"')),
    ).toHaveLength(MAX_GATEWAY_BODY_BYTES - 2);
  });
  it.each([{}, { "content-length": "1" }])(
    "rejects oversized bodies regardless of length header %j",
    async (headers) => {
      await expect(
        readBoundedJson(request('"' + "a".repeat(MAX_GATEWAY_BODY_BYTES) + '"', headers)),
      ).rejects.toMatchObject({ status: 413 });
    },
  );
  it("counts UTF-8 bytes rather than characters", async () => {
    await expect(
      readBoundedJson(request(JSON.stringify("é".repeat(MAX_GATEWAY_BODY_BYTES / 2)))),
    ).rejects.toMatchObject({ status: 413 });
  });
  it.each([
    ["-1", 400],
    ["invalid", 400],
    ["999999999999999999999", 413],
  ])("rejects invalid declared size %s", async (length, status) => {
    await expect(
      readBoundedJson(request("{}", { "content-length": String(length) })),
    ).rejects.toMatchObject({ status });
  });
  it("cancels a chunked stream at the limit", async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.enqueue(new Uint8Array(8193));
      },
      cancel,
    });
    await expect(
      readBoundedJson({ headers: new Headers(), body } as Request),
    ).rejects.toMatchObject({ status: 413 });
    expect(cancel).toHaveBeenCalledOnce();
  });
  it("times out a stalled stream and cancels it", async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({ start() {}, cancel });
    const result = expect(
      readBoundedJson({ headers: new Headers(), body } as Request),
    ).rejects.toMatchObject({ status: 408 });
    await vi.advanceTimersByTimeAsync(GATEWAY_BODY_TIMEOUT_MS);
    await result;
    expect(cancel).toHaveBeenCalledOnce();
  });
  it("rejects malformed JSON and compressed input", async () => {
    await expect(readBoundedJson(request("{"))).rejects.toMatchObject({ status: 400 });
    await expect(
      readBoundedJson(request("{}", { "content-encoding": "gzip" })),
    ).rejects.toMatchObject({ status: 415 });
  });
});
