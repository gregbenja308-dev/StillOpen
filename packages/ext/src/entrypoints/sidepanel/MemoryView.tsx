import { ChatBox } from "./ChatBox";
import { closeOkHosts, keepHosts } from "@/lib/memory";
import type { ChatResponse, MemoryDump } from "@/lib/schema";

type Rule = { host_suffix?: string; close_policy?: string; hits?: number; source?: string; phrase?: string };
type Host = {
  host_suffix?: string;
  user_closed?: number;
  stillopen_closed?: number;
  kept?: number;
  last_action?: string;
};
type Mutation = {
  mutation_id?: string;
  summary?: string;
  kind?: string;
  source?: string;
  created_at?: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
};
type Statement = { statement_id?: string; text?: string; active?: boolean };
type Turn = { turn_id?: string; role?: string; text?: string; mutations?: string[] };

function when(iso: string | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function MemoryView({
  dump,
  onChat,
}: {
  dump: MemoryDump | null;
  onChat: (result: ChatResponse, message: string) => void;
}) {
  const profile = dump?.profile;
  const rules = (profile?.rules ?? []) as Rule[];
  const hosts = (profile?.hosts ?? []) as Host[];
  const mutations = (profile?.mutations ?? []) as Mutation[];
  const statements = (profile?.statements ?? []) as Statement[];
  const chats = (profile?.chats ?? []) as Turn[];
  const kept = keepHosts(profile);
  const closeOk = closeOkHosts(profile);

  return (
    <div className="memory">
      <section className="panel">
        <p className="kicker">Chat</p>
        <h2>Tell it what to close</h2>
        <p className="hint">Ask to close a kind of tab. You’ll see the matches on the Workbench.</p>
        <ChatBox onApplied={onChat} />
      </section>

      {(dump?.scheduled ?? []).filter((row: { status?: string }) => row.status === "pending").length ? (
        <section className="panel">
          <p className="kicker">Scheduled closes</p>
          <h2>Waiting on a timer</h2>
          <ul className="site-list">
            {(dump?.scheduled ?? [])
              .filter((row: { status?: string }) => row.status === "pending")
              .map((row: { schedule_id?: string; label?: string; prompt?: string; run_at?: string; titles?: string[] }) => (
                <li key={row.schedule_id}>
                  <span className="title">{row.label || row.prompt}</span>
                  <span className="host">
                    {when(row.run_at)} · {(row.titles ?? []).length} tabs
                  </span>
                </li>
              ))}
          </ul>
        </section>
      ) : null}

      <section className="panel">
        <p className="kicker">Where it is stored</p>
        <h2>{dump?.storage.engine ?? "MemoryBank"}</h2>
        <p className="hint">{dump?.storage.note}</p>
        <p className="hint">
          Original URLs for Undo live in <code>chrome.storage.session</code> on this laptop. The
          bank only stores redacted title + host + path.
        </p>
        <dl className="store">
          <div>
            <dt>Backend</dt>
            <dd>{dump?.storage.backend ?? "—"}</dd>
          </div>
          <div>
            <dt>Path</dt>
            <dd className="mono">{dump?.storage.path ?? ".stillopen/bank.json"}</dd>
          </div>
          <div>
            <dt>Collections</dt>
            <dd>{(dump?.storage.collections ?? []).join(", ")}</dd>
          </div>
          <div>
            <dt>Habit fields</dt>
            <dd>{(dump?.storage.habit_fields ?? []).join(", ")}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <p className="kicker">What we believe now</p>
        <h2>Living profile</h2>
        <ul className="beliefs">
          <li>
            Unused cutoff: <strong>{profile?.stale_cutoff_days ?? 7} days</strong>
          </li>
          <li>Keep: {kept.length ? kept.join(", ") : "nothing pinned yet"}</li>
          <li>Ok to close: {closeOk.length ? closeOk.join(", ") : "waiting for closes or chat"}</li>
        </ul>
        {rules.length ? (
          <ul className="site-list">
            {rules.map((rule) => (
              <li key={rule.host_suffix}>
                <span className="title">{rule.host_suffix}</span>
                <span className="host">
                  {rule.close_policy} · {rule.hits ?? 1} hit{(rule.hits ?? 1) === 1 ? "" : "s"} ·{" "}
                  {rule.source}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {hosts.length ? (
          <>
            <p className="kicker" style={{ marginTop: 14 }}>
              Learned from closes
            </p>
            <ul className="site-list">
              {hosts.map((host) => (
                <li key={host.host_suffix}>
                  <span className="title">{host.host_suffix}</span>
                  <span className="host">
                    you closed {host.user_closed ?? 0} · Still Open closed {host.stillopen_closed ?? 0}{" "}
                    · kept {host.kept ?? 0}
                    {host.last_action ? ` · last ${host.last_action}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="hint">Close a tab yourself, or let Still Open close one, and a host row appears.</p>
        )}
      </section>

      <section className="panel">
        <p className="kicker">Mutations</p>
        <h2>How the bank just changed</h2>
        {mutations.length === 0 ? (
          <p className="hint">No writes yet. Chat or close a tab.</p>
        ) : (
          <ol className="timeline">
            {mutations.map((row) => (
              <li key={row.mutation_id ?? row.summary}>
                <p className="title">{row.summary}</p>
                <p className="host">
                  {row.kind} · {row.source} · {when(row.created_at)}
                </p>
                {row.before && row.after ? (
                  <p className="mono diff">
                    {JSON.stringify(row.before)} → {JSON.stringify(row.after)}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>

      {statements.length ? (
        <section className="panel">
          <p className="kicker">Said in chat</p>
          <ul className="site-list">
            {statements.map((row) => (
              <li key={row.statement_id}>
                <span className="title">{row.text}</span>
                <span className="host">{row.active ? "active" : "not parsed"}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {chats.length ? (
        <section className="panel">
          <p className="kicker">Chat log</p>
          <ul className="chat-log">
            {chats.map((turn) => (
              <li key={turn.turn_id} className={turn.role}>
                <span className="kicker">{turn.role}</span>
                <p>{turn.text}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {profile ? (
        <section className="panel">
          <p className="kicker">Raw document</p>
          <h2>habits/{profile.user_id}</h2>
          <pre className="json">{JSON.stringify(profile, null, 2)}</pre>
        </section>
      ) : (
        <p className="status">API must be running at 127.0.0.1:8080 to show the bank.</p>
      )}
    </div>
  );
}
