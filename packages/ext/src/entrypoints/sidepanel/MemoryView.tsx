import { closeOkHosts, keepHosts } from "@/lib/memory";
import type { MemoryDump } from "@/lib/schema";

type Host = {
  host_suffix?: string;
  user_closed?: number;
  stillopen_closed?: number;
  kept?: number;
};
type Mutation = {
  mutation_id?: string;
  summary?: string;
  kind?: string;
  created_at?: string;
};

function when(iso: string | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function MemoryView({ dump }: { dump: MemoryDump | null }) {
  const profile = dump?.profile;
  const hosts = (profile?.hosts ?? []) as Host[];
  const mutations = (profile?.mutations ?? []) as Mutation[];
  const kept = keepHosts(profile);
  const closeOk = closeOkHosts(profile);

  return (
    <div className="memory">
      <section className="panel">
        <p className="kicker">Memory · {dump?.storage.backend ?? "local"}</p>
        <h2>Taught</h2>
        <ul className="beliefs">
          <li>Keep: {kept.length ? kept.join(", ") : "—"}</li>
          <li>Ok to close: {closeOk.length ? closeOk.join(", ") : "—"}</li>
        </ul>
        {hosts.length ? (
          <ul className="site-list">
            {hosts.map((host) => (
              <li key={host.host_suffix}>
                <span className="title">{host.host_suffix}</span>
                <span className="host">
                  you {host.user_closed ?? 0} · app {host.stillopen_closed ?? 0} · kept {host.kept ?? 0}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="panel">
        <p className="kicker">Recent</p>
        {mutations.length === 0 ? (
          <p className="hint">Mark a task still going, or restore, and a row appears.</p>
        ) : (
          <ol className="timeline">
            {mutations.slice(0, 12).map((row) => (
              <li key={row.mutation_id ?? row.summary}>
                <p className="title">{row.summary}</p>
                <p className="host">
                  {row.kind} · {when(row.created_at)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
