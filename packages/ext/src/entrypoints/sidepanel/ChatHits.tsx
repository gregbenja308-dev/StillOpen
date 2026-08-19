import { useMemo, useState } from "react";

import type { MatchedTab } from "@/lib/schema";

export function ChatHits({
  label,
  matches,
  busy,
  onClose,
  onDismiss,
}: {
  label: string;
  matches: MatchedTab[];
  busy: boolean;
  onClose: (tabIds: number[]) => void;
  onDismiss: () => void;
}) {
  const [checked, setChecked] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(matches.map((row) => [row.tab_id, true])),
  );
  const selected = useMemo(
    () => matches.filter((row) => checked[row.tab_id]),
    [matches, checked],
  );

  return (
    <section className="panel chat-hits" aria-label="Confirm close">
      <div className="panel-head">
        <h2>{matches.length ? `${matches.length} tabs` : "Nothing matches"}</h2>
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
      {matches.length ? (
        <>
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
          <div className="actions">
            <button
              type="button"
              className="primary"
              disabled={busy || selected.length === 0}
              onClick={() => onClose(selected.map((row) => row.tab_id))}
            >
              Close {selected.length}
            </button>
          </div>
        </>
      ) : (
        <p className="hint">No open tabs match {label || "that"}.</p>
      )}
    </section>
  );
}
