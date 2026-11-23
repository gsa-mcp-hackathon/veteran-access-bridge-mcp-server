import { useState } from "react";

export function PrivateIdentityField({
  ready,
  error,
  submit,
}: {
  ready: boolean;
  error: string;
  submit: (digits: string) => Promise<boolean>;
}) {
  const [digits, setDigits] = useState("");
  const [sending, setSending] = useState(false);
  return (
    <form
      className="mb-3 rounded-lg border border-white/30 p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!ready || sending || !/^[0-9]{4}$/.test(digits)) return;
        const value = digits;
        setDigits("");
        setSending(true);
        try {
          await submit(value);
        } finally {
          setSending(false);
        }
      }}
    >
      <label htmlFor="private-identity-digits" className="text-sm font-semibold">
        Last four digits of test SSN
      </label>
      <p className="my-2 text-xs">
        Enter privately. Do not say the digits aloud. Your microphone is muted during this step.
      </p>
      <input
        id="private-identity-digits"
        type="password"
        inputMode="numeric"
        pattern="[0-9]{4}"
        maxLength={4}
        autoComplete="off"
        spellCheck={false}
        value={digits}
        disabled={!ready || sending}
        onChange={(e) => {
          if (/^[0-9]{0,4}$/.test(e.target.value)) setDigits(e.target.value);
        }}
        className="my-2 w-full rounded-md bg-white p-2 text-slate-900"
        aria-describedby="private-identity-status"
      />
      <button
        type="submit"
        disabled={!ready || sending || digits.length !== 4}
        className="rounded-md bg-cyan-700 px-3 py-2 text-sm text-white disabled:opacity-50"
      >
        {sending ? "Checking…" : "Verify privately"}
      </button>
      <p id="private-identity-status" role="status" className="mt-2 text-xs">
        {error ||
          (!ready
            ? "Preparing private entry…"
            : "Digits are hidden and are not added to the conversation.")}
      </p>
    </form>
  );
}
