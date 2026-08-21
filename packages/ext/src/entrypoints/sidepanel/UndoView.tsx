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

export function UndoView({
  batches,
  busy,
  onRestore,
}: {
  batches: CloseBatch[];
  busy: boolean;
  onRestore: (batchId: string) => void;
}) {
  return (
    <div className="memory">
      {batches.length === 0 ? (
        <section className="panel undo-dock">
          <p className="kicker">Restore</p>
          <h2>Nothing to reopen</h2>
          <p className="hint">Closed tasks from the last month land here.</p>
        </section>
      ) : (
        batches.map((batch) => (
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
            <ul className="site-list">
              {batch.rows.slice(0, 6).map((row) => (
                <li key={`${row.window_id}-${row.tab_id}-${row.url}`}>
                  <span className="title">{row.title || hostOf(row.url)}</span>
                  <span className="host">{hostOf(row.url)}</span>
                </li>
              ))}
            </ul>
            {batch.notes?.trim() ? <p className="restore-note">{batch.notes}</p> : null}
          </section>
        ))
      )}
    </div>
  );
}
