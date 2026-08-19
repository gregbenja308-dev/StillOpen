import { FormEvent, useState } from "react";

import { chatMemory } from "@/lib/api";
import type { ScanReply } from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type { ChatResponse } from "@/lib/schema";

export function ChatBox({
  onApplied,
}: {
  onApplied: (result: ChatResponse, message: string) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const snap = await send<ScanReply>({ type: "SCAN" });
      const tabs = snap.ok ? snap.tabs : [];
      const result = await chatMemory(message, tabs);
      setText("");
      onApplied(result, message);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="chat" onSubmit={onSubmit}>
      <label className="field">
        Close by asking
        <input
          type="text"
          value={text}
          maxLength={500}
          disabled={busy}
          onChange={(event) => setText(event.target.value)}
          placeholder="Delete any news tabs"
        />
      </label>
      <button type="submit" className="primary" disabled={busy || !text.trim()}>
        {busy ? "Finding…" : "Find matching tabs"}
      </button>
      {error ? <p className="status">{error}</p> : null}
    </form>
  );
}
