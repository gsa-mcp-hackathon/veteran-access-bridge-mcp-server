import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Room } from "livekit-client";
import { PrivateIdentityField } from "../components/msa/private-identity-field";
import { identityRequest } from "../components/msa/use-private-identity";

vi.mock("livekit-client", () => ({ ParticipantKind: { AGENT: 4 } }));
afterEach(cleanup);

it("masks and clears digits before sending and never renders their text", async () => {
  const submit = vi.fn(async () => true);
  render(<PrivateIdentityField ready error="" submit={submit} />);
  const input = screen.getByLabelText("Last four digits of test SSN") as HTMLInputElement;
  expect(input.type).toBe("password");
  expect(input.autocomplete).toBe("off");
  fireEvent.change(input, { target: { value: "0067" } });
  expect(screen.queryByText("0067")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Verify privately" }));
  expect(input.value).toBe("");
  await waitFor(() => expect(submit).toHaveBeenCalledWith("0067"));
});

it("does not allow input before the microphone is muted", () => {
  render(<PrivateIdentityField ready={false} error="" submit={vi.fn()} />);
  expect((screen.getByLabelText("Last four digits of test SSN") as HTMLInputElement).disabled).toBe(
    true,
  );
});

describe("addressed private RPC", () => {
  function room(agents = 1, response = '{"required":false}') {
    const performRpc = vi.fn(async () => response);
    const sendText = vi.fn();
    const r = {
      remoteParticipants: new Map(
        Array.from({ length: agents }, (_, i) => [String(i), { identity: `agent-${i}`, kind: 4 }]),
      ),
      localParticipant: { performRpc, sendText },
    } as unknown as Room;
    return { r, performRpc, sendText };
  }
  it("sends only to one agent and never broadcasts or captions digits", async () => {
    const { r, performRpc, sendText } = room();
    expect(await identityRequest(r, "0067")).toBe(false);
    expect(performRpc).toHaveBeenCalledWith({
      destinationIdentity: "agent-0",
      method: "vab.private-identity",
      payload: '{"action":"submit","digits":"0067"}',
      responseTimeout: 30000,
    });
    expect(sendText).not.toHaveBeenCalled();
  });
  it.each([0, 2])("rejects an absent or ambiguous agent %s", async (count) => {
    const { r, performRpc } = room(count);
    await expect(identityRequest(r, "0067")).rejects.toThrow();
    expect(performRpc).not.toHaveBeenCalled();
  });
  it.each(["67", "123456789", "１２３４", "0067 "])(
    "rejects malformed private input",
    async (digits) => {
      const { r, performRpc } = room();
      await expect(identityRequest(r, digits)).rejects.toThrow();
      expect(performRpc).not.toHaveBeenCalled();
    },
  );
  it("rejects a malformed state response", async () => {
    await expect(identityRequest(room(1, '{"required":"false"}').r)).rejects.toThrow();
  });
});
