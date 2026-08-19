import { FormEvent, useState } from "react";

import { chatMemory } from "@/lib/api";
import type { SnapshotReply } from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type { ChatResponse } from "@/lib/schema";

export function ChatBox({
  busy: parentBusy,
  onApplied,
}: {
  busy?: boolean;
  onApplied: (result: ChatResponse, message: string) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");
  const locked = busy || parentBusy;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const snap = await send<SnapshotReply>({ type: "SNAPSHOT" });
      const tabs = snap.ok ? snap.tabs : [];
      const result = await chatMemory(message, tabs);
      setText("");
      setReply(result.reply);
      onApplied(result, message);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="chat-row" onSubmit={onSubmit}>
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
      {reply ? <p className="chat-reply">{reply}</p> : null}
      {error ? <p className="status">{error}</p> : null}
    </form>
  );
}
