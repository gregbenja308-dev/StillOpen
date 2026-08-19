import type { OpenTask } from "@/lib/schema";

export function Workbench({
  tasks,
  scanning,
  busy,
  onRefresh,
  onDemo,
  onDone,
  onKeepGoing,
}: {
  tasks: OpenTask[];
  scanning: boolean;
  busy: boolean;
  onRefresh: () => void;
  onDemo: () => void;
  onDone: (task: OpenTask) => void;
  onKeepGoing: (task: OpenTask) => void;
}) {
  return (
    <>
      <header>
        <div className="panel-head">
          <div>
            <h1>Still Open</h1>
            <p className="lede">Done with a task? Close its tabs.</p>
          </div>
          <div className="select-row">
            <button type="button" disabled={busy} onClick={onDemo}>
              Demo
            </button>
            <button type="button" disabled={busy || scanning} onClick={onRefresh}>
              {scanning ? "…" : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      {tasks.length === 0 ? (
        <section className="panel">
          <p className="hint">{scanning ? "Reading tabs…" : "No open tasks in this window."}</p>
        </section>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.task_id} className={`task-card ${task.kind}`}>
              <div className="task-top">
                <h2>{task.label}</h2>
                <span className="task-count">{task.tab_ids.length}</span>
              </div>
              <p className="task-meta">
                {task.quiet ? <span className="quiet">quiet</span> : null}
                {task.hosts.slice(0, 3).join(" · ")}
                {task.hosts.length > 3 ? "…" : ""}
              </p>
              {task.kind === "protected" ? (
                <p className="hint">Stays. Never sent to a model.</p>
              ) : (
                <div className="actions">
                  <button type="button" disabled={busy} onClick={() => onKeepGoing(task)}>
                    Still going
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() => onDone(task)}
                  >
                    I&apos;m done
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
