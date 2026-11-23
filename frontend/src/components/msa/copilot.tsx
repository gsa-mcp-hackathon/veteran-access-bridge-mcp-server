import { useState } from "react";
import { PanelRightClose, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { copilotAnswer } from "@/lib/encounter-work";
import type { Live } from "./use-live";
export function Copilot({
  live,
  exception,
  onClose,
}: {
  live: Live;
  exception: boolean;
  onClose: () => void;
}) {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<{ question: string; answer: string }[]>([]);
  const send = (question: string) => {
    if (!question.trim()) return;
    setTurns((old) => [
      ...old,
      { question: question.trim(), answer: copilotAnswer(question, live, exception) },
    ]);
    setInput("");
  };
  return (
    <aside
      aria-label="Private staff copilot"
      className="copilot-rail flex min-w-0 flex-col bg-surface"
    >
      <header className="flex items-center justify-between gap-2 bg-header px-4 py-3 text-header-foreground">
        <div>
          <h2 className="font-semibold">Chat with Avery</h2>
          <p className="mt-1 text-xs text-canvas-muted">Private MSA copilot · staff only</p>
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="size-11 shrink-0 text-header-foreground hover:bg-canvas-raised hover:text-header-foreground"
          aria-label="Collapse Chat with Avery"
          title="Collapse Chat with Avery"
          onClick={onClose}
        >
          <PanelRightClose />
        </Button>
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        <div className="flex gap-2 text-sm">
          <Sparkles className="mt-1 size-4 shrink-0 text-primary" />
          <p>
            {exception
              ? "I can help you review this exception safely."
              : "I'm handling this routine encounter. What would you like to review?"}
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Local scripted staff answers. Not sent to the Veteran; no AI service connection.
        </p>
        <div className="flex flex-col items-start">
          {[
            "Confirm the current status and next steps",
            "Eligibility evidence",
            "Document progress",
          ].map((prompt) => (
            <Button
              key={prompt}
              variant="ghost"
              className="min-h-11 h-auto justify-start whitespace-normal px-2 text-left text-sm text-primary underline-offset-4 hover:underline"
              onClick={() => send(prompt)}
            >
              {prompt}
            </Button>
          ))}
        </div>
        <div aria-live="polite" className="space-y-4">
          {turns.map((turn, index) => (
            <div key={index} className="space-y-2 text-sm">
              <p className="rounded-md bg-secondary p-3">
                <strong>MSA</strong>
                <br />
                {turn.question}
              </p>
              <p className="border-l-2 border-primary pl-3 leading-6">
                <strong>Avery · staff fixture</strong>
                <br />
                {turn.answer}
              </p>
            </div>
          ))}
        </div>
      </div>
      <form
        className="border-t p-4"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <label htmlFor="staff-question" className="mb-2 block text-xs font-medium">
          Private message to Avery
        </label>
        <div className="flex gap-2">
          <input
            id="staff-question"
            className="min-h-11 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm"
            placeholder="Ask about this encounter…"
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
          <Button
            type="submit"
            size="icon"
            className="size-11 shrink-0"
            disabled={!input.trim()}
            aria-label="Send private message"
          >
            <Send />
          </Button>
        </div>
      </form>
    </aside>
  );
}
