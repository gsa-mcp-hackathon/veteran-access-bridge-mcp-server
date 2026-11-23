import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AveryEmbeddedChat,
  AVERY_M64_EMBED,
  isEmbedToken,
} from "@/components/msa/avery-embedded-chat";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (window as Window & { wxOConfiguration?: unknown }).wxOConfiguration;
  delete (window as Window & { wxoLoader?: unknown }).wxoLoader;
});

const fakeToken = `eyJhbGciOiJSUzI1NiJ9.${"a".repeat(350)}.sig`;
const tokenBody = {
  identityToken: fakeToken,
  expiresAt: Math.floor(Date.now() / 1000) + 600,
};

describe("IBM Avery M6.4 inline embed", () => {
  it("uses the actual deployed Live M6.4 agent and recognizes only fresh JWTs", () => {
    expect(AVERY_M64_EMBED.agentId).toBe("b38da637-92e4-4c5c-9c7e-d4f8dce28160");
    expect(AVERY_M64_EMBED.agentEnvironmentId).toBe("f8e848fa-c93b-4b92-b760-96abcd4c4f37");
    expect(isEmbedToken(tokenBody)).toBe(true);
    expect(isEmbedToken({ ...tokenBody, expiresAt: 0 })).toBe(false);
    expect(isEmbedToken({ ...tokenBody, identityToken: "bad" })).toBe(false);
  });

  it("does not fetch a token or render a floating launcher until user starts", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AveryEmbeddedChat />);
    expect(screen.getByRole("button", { name: "Start with Avery" })).toBeInTheDocument();
    expect(screen.getByLabelText("Avery IBM embedded conversation")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(document.querySelector('[data-vab-wxo="true"]')).toBeNull();
  });

  it("fails closed with a useful message if sandbox JWT issuance is disabled", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AveryEmbeddedChat />);
    fireEvent.click(screen.getByRole("button", { name: "Start with Avery" }));
    await waitFor(() => {
      expect(
        screen.getByText(/secure sandbox connection has not been enabled/i),
      ).toBeInTheDocument();
    });
    const [path, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/avery-embed-token");
    expect(init.body).toBe("{}");
    expect(new Headers(init.headers).get("x-vab-guest-embed")).toBe("1");
  });

  it("mounts the native IBM conversation inside the supplied container", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(tokenBody), { status: 200 })),
    );
    const changeView = vi.fn(async () => undefined);
    const destroy = vi.fn();
    type Listener = (event: { authToken?: string }, instance: unknown) => void;
    const listeners: Record<string, Listener> = {};
    const instance = {
      changeView,
      destroy,
      updateAuthToken: vi.fn(),
      on: vi.fn((event: string, cb: (e: { authToken?: string }, instance: unknown) => void) => {
        listeners[event] = cb;
      }),
    };
    const browser = window as Window & {
      wxOConfiguration?: {
        layout: { form: string; customElement: HTMLElement };
        rootElementID: string;
        showLauncher: boolean;
        chatOptions: { agentId: string; onLoad: (chat: typeof instance) => void };
        token: string;
      };
      wxoLoader?: { init: () => void };
    };
    browser.wxoLoader = {
      init: () => browser.wxOConfiguration?.chatOptions.onLoad(instance),
    };
    render(<AveryEmbeddedChat />);
    fireEvent.click(screen.getByRole("button", { name: "Start with Avery" }));
    await waitFor(() =>
      expect(changeView).toHaveBeenCalledWith({ launcher: false, mainWindow: true }),
    );
    expect(browser.wxOConfiguration?.layout.form).toBe("custom");
    expect(browser.wxOConfiguration?.rootElementID).toBe("root");
    expect(browser.wxOConfiguration?.showLauncher).toBe(false);
    expect(browser.wxOConfiguration?.layout.customElement.id).toBe("root");
    expect(browser.wxOConfiguration?.chatOptions.agentId).toBe(AVERY_M64_EMBED.agentId);
    expect(browser.wxOConfiguration?.token).toBe(fakeToken);
    await act(async () => {
      await listeners["authTokenNeeded"]?.({}, instance);
    });
    expect(instance.updateAuthToken).toHaveBeenCalledWith(fakeToken);
  });
});
