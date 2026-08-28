import { useEffect, useRef, useState } from "react";

import type { CloseBatch } from "@/lib/schema";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function when(ms: number): string {
  const date = new Date(ms);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

function ClosedNote({
  batchId,
  notes,
  onSave,
}: {
  batchId: string;
  notes: string;
  onSave: (batchId: string, notes: string) => void;
}) {
  const [draft, setDraft] = useState(notes);
  const timer = useRef(0);
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) {
      setDraft(notes);
    }
  }, [notes]);

  useEffect(() => {
    return () => window.clearTimeout(timer.current);
  }, []);

  function persist(next: string) {
    window.clearTimeout(timer.current);
    onSave(batchId, next);
  }

  return (
    <label className="closed-note">
      <span className="kicker">Note</span>
      <textarea
        value={draft}
        maxLength={4000}
        rows={3}
        placeholder="Add a note for this finished task…"
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => persist(next), 400);
        }}
        onFocus={() => {
          focused.current = true;
        }}
        onBlur={() => {
          focused.current = false;
          persist(draft);
        }}
      />
    </label>
  );
}

export function UndoView({
  batches,
  busy,
  onRestore,
  onNotes,
}: {
  batches: CloseBatch[];
  busy: boolean;
  onRestore: (batchId: string) => void;
  onNotes: (batchId: string, notes: string) => void;
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? batches.filter((batch) => batch.label.toLowerCase().includes(needle))
    : batches;

  return (
    <div className="memory">
      {batches.length > 0 ? (
        <label className="closed-search">
          <span className="kicker">Search</span>
          <input
            type="search"
            value={query}
            placeholder="Search by task title"
            aria-label="Search finished tasks by title"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      ) : null}

      {batches.length === 0 ? (
        <section className="panel undo-dock">
          <p className="kicker">Finished</p>
          <h2>Nothing here yet</h2>
          <p className="hint">Finished tasks from the last month land here.</p>
        </section>
      ) : shown.length === 0 ? (
        <section className="panel undo-dock">
          <p className="kicker">Finished</p>
          <h2>No matches</h2>
          <p className="hint">No finished task title matches “{query.trim()}”.</p>
        </section>
      ) : (
        shown.map((batch) => (
          <section key={batch.batch_id} className="panel undo-dock">
            <div className="undo-head">
              <div>
                <p className="kicker">{when(batch.closed_at)}</p>
                <h2>{batch.label}</h2>
              </div>
              <button
                type="button"
                className="primary"
                disabled={busy}
                onClick={() => onRestore(batch.batch_id)}
              >
                Restore {batch.rows.length}
              </button>
            </div>
            <ul className="site-list closed-tabs">
              {batch.rows.slice(0, 6).map((row) => (
                <li key={`${row.window_id}-${row.tab_id}-${row.url}`}>
                  <span className="title">{row.title || hostOf(row.url)}</span>
                  <span className="host">{hostOf(row.url)}</span>
                </li>
              ))}
            </ul>
            {batch.filing_url || batch.audit_url ? (
              <p className="agent-links">
                {batch.filing_url ? (
                  <a href={batch.filing_url} target="_blank" rel="noopener noreferrer">
                    Filing
                  </a>
                ) : null}
                {batch.filing_url && batch.audit_url ? " · " : null}
                {batch.audit_url ? (
                  <a href={batch.audit_url} target="_blank" rel="noopener noreferrer">
                    Audit trail
                  </a>
                ) : null}
                {batch.clerk ? <span className="host"> · clerk: {batch.clerk}</span> : null}
              </p>
            ) : null}
            <ClosedNote batchId={batch.batch_id} notes={batch.notes ?? ""} onSave={onNotes} />
          </section>
        ))
      )}
    </div>
  );
}
