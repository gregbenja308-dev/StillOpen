import { FormEvent, useEffect, useRef, useState } from "react";

import { chatMemory } from "@/lib/api";
import type { ScanReply } from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type { ChatResponse, OpenTask } from "@/lib/schema";

type Turn = { role: "user" | "assistant"; text: string };

export function ChatBox({
  busy: parentBusy,
  tasks,
  onApplied,
}: {
  busy?: boolean;
  tasks: OpenTask[];
  onApplied: (result: ChatResponse, message: string) => void;
}) {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const locked = busy || parentBusy;

  useEffect(() => {
    const node = logRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [turns, busy]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message) {
      return;
    }
    setBusy(true);
    setError("");
    setText("");
    setTurns((prev) => [...prev, { role: "user", text: message }]);
    try {
      const snap = await send<ScanReply>({ type: "SCAN" });
      const tabs = snap.ok ? snap.tabs : [];
      const result = await chatMemory(message, tabs, tasks);
      setTurns((prev) => [...prev, { role: "assistant", text: result.reply }]);
      onApplied(result, message);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="chat-row" onSubmit={onSubmit}>
      {turns.length > 0 || busy ? (
        <div className="chat-log" ref={logRef} role="log" aria-live="polite">
          {turns.map((turn, index) => (
            <p key={`${turn.role}-${index}`} className={turn.role === "user" ? "chat-user" : "chat-reply"}>
              {turn.text}
            </p>
          ))}
          {busy ? <p className="chat-reply chat-pending">Looking…</p> : null}
        </div>
      ) : null}
      <div className="chat-box">
        <textarea
          value={text}
          maxLength={500}
          rows={4}
          disabled={locked}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Ask anything — or close unused 30 days…"
          aria-label="Ask about Still Open"
        />
        <button type="submit" className="chat-ask primary" disabled={locked || !text.trim()}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
      {error ? <p className="status">{error}</p> : null}
    </form>
  );
}
