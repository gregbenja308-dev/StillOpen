import type { RunResponse, UndoRow } from "@/lib/schema";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
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
      <section className="panel undo-dock">
        <div className="undo-head">
          <div>
            <p className="kicker">Restore</p>
            <h2>{rows.length === 0 ? "Nothing to reopen" : plural(rows.length, "tab")}</h2>
          </div>
          <button type="button" className="primary" disabled={busy || rows.length === 0} onClick={onRestore}>
            Restore
          </button>
        </div>
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
          <p className="hint">Closed tabs land here.</p>
        )}
      </section>

      {lastRun?.artifacts.length ? (
        <section className="panel">
          <p className="kicker">Saved</p>
          <ul className="site-list">
            {lastRun.artifacts.map((row) => (
              <li key={row.record_id}>
                <a className="artifact" href={row.url} target="_blank" rel="noreferrer">
                  {row.title || row.kind}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
