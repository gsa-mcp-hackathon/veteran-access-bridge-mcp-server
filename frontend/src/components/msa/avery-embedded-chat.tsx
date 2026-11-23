import { useEffect, useRef, useState } from "react";
import { AudioLines, RotateCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Real watsonx Orchestrate M6.4 Live embed. No second AI agent, no floating
 * launcher, no custom audio capture and no browser-side IBM signing key.
 * Native voice is started using IBM's own voice control inside this panel.
 */
export const AVERY_M64_EMBED = {
  orchestrationID: "<YOUR_ORCHESTRATE_ACCOUNT_ID>_<YOUR_ORCHESTRATE_INSTANCE_ID>",
  hostURL: "https://ca-tor.watson-orchestrate.cloud.ibm.com",
  crn: "crn:v1:bluemix:public:watsonx-orchestrate:ca-tor:a/<YOUR_ORCHESTRATE_ACCOUNT_ID>:<YOUR_ORCHESTRATE_INSTANCE_ID>::",
  agentId: "b38da637-92e4-4c5c-9c7e-d4f8dce28160",
  agentEnvironmentId: "f8e848fa-c93b-4b92-b760-96abcd4c4f37",
} as const;

type EmbedPhase = "idle" | "authorizing" | "loading" | "ready" | "unavailable";
type ChatEvent = { authToken?: string };
type ChatInstance = {
  changeView: (update: { launcher: boolean; mainWindow: boolean }) => Promise<void>;
  on: (eventName: string, listener: (event: ChatEvent, instance: ChatInstance) => void) => void;
  updateAuthToken: (token: string) => void;
  destroy: () => void | Promise<void>;
};

type WxOWindow = Window & {
  wxOConfiguration?: {
    orchestrationID: string;
    hostURL: string;
    crn: string;
    deploymentPlatform: "ibmcloud";
    rootElementID: "root";
    showLauncher: false;
    token: string;
    layout: {
      form: "custom";
      customElement: HTMLElement;
      skin: "next";
      showOrchestrateHeader: false;
      showMaxWidth: true;
    };
    features: { showThreadList: false };
    style: {
      theme: "light";
      primaryColor: string;
      headerColor: string;
      userMessageBackgroundColor: string;
      showBackgroundGradient: false;
      fontFamily: string;
    };
    chatOptions: {
      agentId: string;
      agentEnvironmentId: string;
      onLoad: (instance: ChatInstance) => void;
    };
  };
  wxoLoader?: { init: () => void | Promise<void> };
};

type IdentityToken = { identityToken: string; expiresAt: number };

export function isEmbedToken(value: unknown): value is IdentityToken {
  if (value === null || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data["identityToken"] === "string" &&
    /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(data["identityToken"]) &&
    typeof data["expiresAt"] === "number" &&
    Number.isSafeInteger(data["expiresAt"]) &&
    data["expiresAt"] > Math.floor(Date.now() / 1000)
  );
}

async function fetchEmbedToken(): Promise<string> {
  const response = await fetch("/api/avery-embed-token", {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-VAB-Guest-Embed": "1",
    },
    body: "{}",
  });
  if (!response.ok) {
    if (response.status === 403)
      throw new Error("Avery's secure sandbox connection has not been enabled yet.");
    if (response.status === 429)
      throw new Error("The sandbox guest session limit has been reached. Try again later.");
    throw new Error("Avery's secure connection is unavailable. Check the IBM embed gateway.");
  }
  const payload: unknown = await response.json();
  if (!isEmbedToken(payload)) throw new Error("Avery returned an invalid session token.");
  return payload.identityToken;
}

/**
 * Load the official IBM script once, after an explicit guest action. Do not
 * mutate IBM's shadow DOM or inject undocumented controls into its widget.
 */
function loadIBM(win: WxOWindow): Promise<void> {
  if (win.wxoLoader) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-vab-wxo="true"]');
    const script = existing ?? document.createElement("script");
    const onLoad = () => {
      cleanup();
      if (win.wxoLoader) resolve();
      else reject(new Error("IBM embedded chat loader is unavailable."));
    };
    const onError = () => {
      cleanup();
      reject(new Error("Unable to load IBM's embedded chat."));
    };
    function cleanup() {
      script.removeEventListener("load", onLoad);
      script.removeEventListener("error", onError);
    }
    script.addEventListener("load", onLoad);
    script.addEventListener("error", onError);
    if (!existing) {
      script.setAttribute("data-vab-wxo", "true");
      script.src = `${AVERY_M64_EMBED.hostURL}/wxochat/wxoLoader.js?embed=true`;
      script.async = true;
      document.head.appendChild(script);
    }
  });
}

export function AveryEmbeddedChat() {
  const hostRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<ChatInstance | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<EmbedPhase>("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!attempt) return;
    let cancelled = false;
    const win = window as WxOWindow;
    const host = hostRef.current;
    if (!host) return;

    async function connect() {
      try {
        setPhase("authorizing");
        setError("");
        const initialToken = await fetchEmbedToken();
        if (cancelled) return;
        setPhase("loading");
        win.wxOConfiguration = {
          orchestrationID: AVERY_M64_EMBED.orchestrationID,
          hostURL: AVERY_M64_EMBED.hostURL,
          crn: AVERY_M64_EMBED.crn,
          deploymentPlatform: "ibmcloud",
          rootElementID: "root",
          showLauncher: false,
          token: initialToken,
          layout: {
            form: "custom",
            customElement: host!,
            skin: "next",
            showOrchestrateHeader: false,
            showMaxWidth: true,
          },
          features: { showThreadList: false },
          style: {
            theme: "light",
            primaryColor: "#005ea2",
            headerColor: "#162e51",
            userMessageBackgroundColor: "#d9e8f6",
            showBackgroundGradient: false,
            fontFamily: "IBM Plex Sans, Arial, sans-serif",
          },
          chatOptions: {
            agentId: AVERY_M64_EMBED.agentId,
            agentEnvironmentId: AVERY_M64_EMBED.agentEnvironmentId,
            onLoad(instance) {
              if (cancelled) {
                void instance.destroy();
                return;
              }
              instanceRef.current = instance;
              instance.on("authTokenNeeded", async (event, activeInstance) => {
                try {
                  // Refresh the same HttpOnly guest session; no signing key in the client.
                  const freshToken = await fetchEmbedToken();
                  if (cancelled) return;
                  event.authToken = freshToken;
                  activeInstance.updateAuthToken(freshToken);
                } catch {
                  if (!cancelled) {
                    setError("Avery's secure session expired. Refresh to reconnect.");
                  }
                }
              });
              instance.on("chat:ready", () => {
                if (cancelled) return;
                void instance.changeView({ launcher: false, mainWindow: true });
                setPhase("ready");
              });
              void instance.changeView({ launcher: false, mainWindow: true }).then(
                () => {
                  if (!cancelled) setPhase("ready");
                },
                () => {
                  if (!cancelled) setError("Avery's embedded conversation view could not open.");
                },
              );
            },
          },
        };
        await loadIBM(win);
        if (cancelled) return;
        if (!win.wxoLoader) throw new Error("IBM embedded chat loader is unavailable.");
        await win.wxoLoader.init();
      } catch (cause) {
        if (cancelled) return;
        setPhase("unavailable");
        setError(cause instanceof Error ? cause.message : "Avery did not connect.");
      }
    }
    void connect();
    return () => {
      cancelled = true;
      const instance = instanceRef.current;
      instanceRef.current = null;
      if (instance) void instance.destroy();
      if (win.wxOConfiguration?.layout.customElement === host) {
        delete win.wxOConfiguration;
      }
    };
  }, [attempt]);

  return (
    <div className="relative min-h-[75dvh] w-full bg-white">
      <div
        ref={hostRef}
        id="root"
        className="h-[85dvh] min-h-[600px] w-full lg:h-[100dvh]"
        aria-label="Avery IBM embedded conversation"
      />
      {phase !== "ready" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-white p-6 text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-[#e4f3ff] text-primary">
            <AudioLines className="size-8" aria-hidden="true" />
          </div>
          <div className="max-w-sm">
            <h3 className="text-lg font-semibold">Talk with Avery</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              {phase === "idle"
                ? "Start a secure synthetic appointment conversation. Choose IBM's voice control inside the conversation to speak naturally."
                : phase === "authorizing"
                  ? "Starting your private sandbox session…"
                  : phase === "loading"
                    ? "Opening Avery's IBM conversation…"
                    : error}
            </p>
          </div>
          {(phase === "idle" || phase === "unavailable") && (
            <Button
              size="lg"
              className="min-h-12 gap-2"
              onClick={() => setAttempt((value) => value + 1)}
            >
              {phase === "unavailable" ? (
                <RotateCw className="size-4" />
              ) : (
                <AudioLines className="size-4" />
              )}
              {phase === "unavailable" ? "Retry Avery connection" : "Start with Avery"}
            </Button>
          )}
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <ShieldCheck className="size-4" aria-hidden="true" />
            Sandbox only · Synthetic data · No real VA booking
          </p>
        </div>
      )}
      {phase === "ready" && error && (
        <p
          className="absolute bottom-2 left-2 right-2 rounded-md border border-destructive/30 bg-white p-2 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}
    </div>
  );
}
