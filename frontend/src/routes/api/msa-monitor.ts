import { createFileRoute } from "@tanstack/react-router";
import { GatewayBodyError, readBoundedJson } from "@/lib/bounded-json";
import {
  backendRequest,
  parseGatewayBody,
  projectMonitorBackendFailure,
} from "@/lib/msa-monitor-gateway";
import { authorizeSandboxRequest, type OneClickEnv } from "@/lib/one-click-gate";

/**
 * LOCAL SYNTHETIC sandbox gateway. Disabled unless server-only env is set.
 * Not production MSA auth. No CORS headers are emitted on purpose.
 */
const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

export const Route = createFileRoute("/api/msa-monitor")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const auth = await authorizeSandboxRequest(process.env as OneClickEnv, request);
        if (!auth.ok)
          return json(
            { error: auth.error === "forbidden" ? "forbidden" : "monitor_disabled" },
            403,
          );
        const config = auth.config;
        let body: unknown;
        try {
          body = await readBoundedJson(request);
        } catch (error) {
          return json(
            { error: "invalid_request" },
            error instanceof GatewayBodyError ? error.status : 400,
          );
        }
        const action = parseGatewayBody(body);
        if (!action) return json({ error: "invalid_request" }, 400);
        const { url, init } = backendRequest(config, action);
        try {
          const res = await fetch(url, { ...init, signal: AbortSignal.timeout(10000) });
          if (!res.ok) {
            // Only known backend readiness codes cross the BFF boundary.
            // Unexpected status/body content stays hidden from the browser.
            let errorCode: unknown;
            if (res.status === 409 || res.status === 503) {
              try {
                const body = (await res.json()) as { error?: unknown } | null;
                errorCode = body?.error;
              } catch {
                // An unexpected backend response fails closed.
              }
            }
            const failure = projectMonitorBackendFailure(action, res.status, errorCode);
            return json(failure.body, failure.status);
          }
          return json(await res.json(), 200);
        } catch {
          return json({ error: "backend_unavailable" }, 502);
        }
      },
    },
  },
});
