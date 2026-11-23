import type { AfterCall } from "@/lib/after-call";

export function AfterCallCard({
  result,
  retry,
  complete,
}: {
  result: AfterCall | null;
  retry: () => void;
  complete?: boolean;
}) {
  if (!result) return null;
  return (
    <section
      aria-label="After-call work"
      aria-live="polite"
      className="mt-4 rounded-lg border border-slate-200 bg-white p-4 text-slate-900 shadow-sm"
    >
      <h3 className="font-semibold">
        {result.status === "COMPLETE"
          ? complete === false
            ? "After-call summary saved"
            : "Wrap-up complete"
          : "After-call work"}
      </h3>
      {result.status === "COMPLETE" ? (
        <>
          <p className="mt-2 text-sm">{result.summary}</p>
          <p className="mt-2 break-all text-xs text-slate-600">
            Saved CRM receipt: {result.record_id}
          </p>
          {result.letter && (
            <div className="mt-3 border-t pt-3">
              <a
                className="font-semibold text-blue-800 underline"
                download={result.letter.filename}
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(result.letter.text)}`}
              >
                Download appointment letter
              </a>
              <p className="mt-1 text-xs">Generated · Not sent</p>
              <details className="mt-2 text-sm">
                <summary>Preview letter</summary>
                <pre className="mt-2 whitespace-pre-wrap font-sans">{result.letter.text}</pre>
              </details>
            </div>
          )}
        </>
      ) : result.status === "NOT_SAVED_UNVERIFIED" ? (
        <p className="mt-2 text-sm">
          Call ended without verified identity. No patient CRM note or appointment letter was
          created.
        </p>
      ) : (
        <>
          <p className="mt-2 text-sm">
            {result.status === "PENDING"
              ? "Wrap-up is pending; a saved record is not yet confirmed."
              : "After-call work is unavailable. Staff review is needed."}
          </p>
          <button className="mt-2 min-h-10 rounded border px-3 text-sm" onClick={retry}>
            Retry wrap-up
          </button>
        </>
      )}
    </section>
  );
}
