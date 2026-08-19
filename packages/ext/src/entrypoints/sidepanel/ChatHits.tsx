import { useMemo, useState } from "react";

import type { MatchedTab } from "@/lib/schema";

function tonight(): number {
  const date = new Date();
  date.setHours(21, 0, 0, 0);
  if (date.getTime() <= Date.now()) {
    date.setDate(date.getDate() + 1);
  }
  return date.getTime();
}

function tomorrowMorning(): number {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(9, 0, 0, 0);
  return date.getTime();
}

const PRESETS: Array<{ id: string; label: string; at: () => number }> = [
  { id: "1h", label: "In 1 hour", at: () => Date.now() + 60 * 60 * 1000 },
  { id: "tonight", label: "Tonight 9pm", at: tonight },
  { id: "tomorrow", label: "Tomorrow 9am", at: tomorrowMorning },
  { id: "3d", label: "In 3 days", at: () => Date.now() + 3 * 24 * 60 * 60 * 1000 },
  { id: "7d", label: "In 1 week", at: () => Date.now() + 7 * 24 * 60 * 60 * 1000 },
];

export function ChatHits({
  prompt,
  label,
  matches,
  busy,
  onCloseNow,
  onFileThenClose,
  onSchedule,
  onDismiss,
}: {
  prompt: string;
  label: string;
  matches: MatchedTab[];
  busy: boolean;
  onCloseNow: (tabIds: number[]) => void;
  onFileThenClose: (tabIds: number[]) => void;
  onSchedule: (tabIds: number[], whenMs: number) => void;
  onDismiss: () => void;
}) {
  const [checked, setChecked] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(matches.map((row) => [row.tab_id, true])),
  );
  const [custom, setCustom] = useState("");
  const selected = useMemo(
    () => matches.filter((row) => checked[row.tab_id]),
    [matches, checked],
  );

  if (matches.length === 0) {
    return (
      <section className="panel chat-hits" aria-label="Chat results">
        <p className="kicker">Results</p>
        <h2>No {label || "matching tabs"} open</h2>
        <p className="hint">Nothing in this Chrome matches “{prompt}”.</p>
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </section>
    );
  }

  return (
    <section className="panel chat-hits" aria-label="Chat results">
      <div className="panel-head">
        <div>
          <p className="kicker">Results</p>
          <h2>
            {matches.length} {label || "matching tabs"}
          </h2>
        </div>
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
      <p className="prompt">
        File writes titles and URLs into a Google Doc (or a Calendar hold), proves it exists, then
        closes. Close now skips the Doc. Uncheck any you want to keep.
      </p>
      <div className="select-row">
        <button
          type="button"
          onClick={() => setChecked(Object.fromEntries(matches.map((row) => [row.tab_id, true])))}
        >
          Select all
        </button>
        <button
          type="button"
          onClick={() => setChecked(Object.fromEntries(matches.map((row) => [row.tab_id, false])))}
        >
          Select none
        </button>
      </div>
      <ul className="site-list pick scroll">
        {matches.map((row) => (
          <li key={row.tab_id}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(checked[row.tab_id])}
                onChange={(event) =>
                  setChecked((prev) => ({ ...prev, [row.tab_id]: event.target.checked }))
                }
              />
              <span>
                <span className="title">{row.title}</span>
                <span className="host">{row.host}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <div className="actions close-now">
        <button
          type="button"
          className="primary"
          disabled={busy || selected.length === 0}
          onClick={() => onFileThenClose(selected.map((row) => row.tab_id))}
        >
          File, then close {selected.length}
        </button>
        <button
          type="button"
          disabled={busy || selected.length === 0}
          onClick={() => onCloseNow(selected.map((row) => row.tab_id))}
        >
          Close {selected.length} now
        </button>
      </div>
      <p className="kicker" style={{ marginTop: 14 }}>
        Or schedule
      </p>
      <div className="select-row">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            disabled={busy || selected.length === 0}
            onClick={() => onSchedule(selected.map((row) => row.tab_id), preset.at())}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <label className="field">
        Custom time
        <input
          type="datetime-local"
          value={custom}
          onChange={(event) => setCustom(event.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={busy || selected.length === 0 || !custom}
        onClick={() => {
          const whenMs = new Date(custom).getTime();
          if (!Number.isFinite(whenMs) || whenMs <= Date.now()) {
            return;
          }
          onSchedule(selected.map((row) => row.tab_id), whenMs);
        }}
      >
        Schedule custom
      </button>
    </section>
  );
}
