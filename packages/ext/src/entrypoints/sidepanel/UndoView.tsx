import type { RunResponse, UndoRow } from "@/lib/schema";
import { hostOf } from "@/lib/stale";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function UndoView({
  rows,
  lastRun,
  busy,
  onRestore,
}: {
  rows: UndoRow[];
  lastRun: RunResponse | null;
  busy: boolean;
  onRestore: () => void;
}) {
  return (
    <div className="memory">
      <section className="panel undo-dock" aria-label="Restore closed tabs">
        <div className="undo-head">
          <div>
            <p className="kicker">Restore</p>
            <h2>
              {rows.length === 0
                ? "Nothing waiting to reopen"
                : `Restore ${plural(rows.length, "closed tab")}?`}
            </h2>
          </div>
          <button
            type="button"
            className="primary"
            disabled={busy || rows.length === 0}
            onClick={onRestore}
          >
            Restore these
          </button>
        </div>
        <p className="hint">
          These exact tabs reopen. Original URLs stay in this Chrome session — they never go to the
          API. Restore also teaches Still Open to keep those sites.
        </p>
        {rows.length > 0 ? (
          <ul className="site-list">
            {rows.map((row) => (
              <li key={`${row.window_id}-${row.tab_id}`}>
                <span className="title">{row.title || hostOf(row.url)}</span>
                <span className="host">{hostOf(row.url)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="status">Close something from the Workbench and it will land here.</p>
        )}
      </section>

      {lastRun?.artifacts.length ? (
        <section className="panel" aria-label="Last filed artifacts">
          <p className="kicker">Filed into Google</p>
          <h2>The work is in a Doc, not the tab strip</h2>
          <p className="hint">
            File means: write the titles and URLs into Google (a comparison Doc, or a Calendar
            hold), prove the file exists, then close. If the Doc fails, tabs stay open.
          </p>
          <ul className="site-list">
            {lastRun.artifacts.map((row) => (
              <li key={row.record_id}>
                <a className="artifact" href={row.url} target="_blank" rel="noreferrer">
                  {row.title || row.kind} · {row.url}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section className="panel">
          <p className="kicker">What File means</p>
          <h2>Keep the work, lose the tabs</h2>
          <p className="hint">
            House shopping becomes a Google Doc of the listings you were comparing. A tracking page
            becomes a Calendar hold. Then — and only then — those tabs may close. Close now skips
            that and just kills the tab.
          </p>
        </section>
      )}
    </div>
  );
}
