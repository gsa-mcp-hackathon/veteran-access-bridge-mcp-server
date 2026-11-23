import { useEffect, useState } from "react";

export function ReviewerSignOut({ callActive }: { callActive: boolean }) {
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/reviewer-session", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => response.ok && (await response.json()).authenticated === true)
      .then((active) => {
        if (!controller.signal.aborted) setEnabled(active);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  if (!enabled) return null;
  return (
    <button
      type="button"
      disabled={callActive}
      className="rounded-md border border-white/40 px-3 py-1.5 disabled:opacity-50"
      title={callActive ? "End the call before signing out" : "End your reviewer session"}
      onClick={async () => {
        try {
          const response = await fetch("/api/reviewer-logout", { method: "POST" });
          if (!response.ok) throw new Error("logout_failed");
          window.location.assign("/login");
        } catch {
          setError(true);
        }
      }}
    >
      {error ? "Retry sign out" : "Sign out"}
    </button>
  );
}
