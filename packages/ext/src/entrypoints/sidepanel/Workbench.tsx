import { useEffect, useState } from "react";

import type { OpenTask, TabSnapshot } from "@/lib/schema";
import { hostOf } from "@/lib/stale";

export function Workbench({
  tasks,
  live,
  loose,
  scanning,
  busy,
  burst,
  onRefresh,
  onDemo,
  onNewTask,
  onDone,
  onRename,
  onIgnore,
  onMove,
  onDropLoose,
}: {
  tasks: OpenTask[];
  live: TabSnapshot[];
  loose: TabSnapshot[];
  scanning: boolean;
  busy: boolean;
  burst: boolean;
  onRefresh: () => void;
  onDemo: () => void;
  onNewTask: () => void;
  onDone: (task: OpenTask) => void;
  onRename: (taskId: string, label: string) => void;
  onIgnore: (taskId: string, tabId: number) => void;
  onMove: (tabId: number, fromId: string, toId: string) => void;
  onDropLoose: (tabId: number, toId: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const byId = new Map(live.map((tab) => [tab.tab_id, tab]));

  return (
    <>
      {burst ? <Confetti /> : null}
      <header>
        <div className="panel-head">
          <div>
            <h1>Still Open</h1>
            <p className="lede">Done with a task? Close its tabs.</p>
          </div>
          <div className="select-row">
            <button type="button" disabled={busy} onClick={onDemo}>
              Demo Seed
            </button>
            <button type="button" disabled={busy || scanning} onClick={onRefresh}>
              {scanning ? "…" : "Rescan"}
            </button>
          </div>
        </div>
      </header>

      {tasks.length === 0 && !scanning ? (
        <section className="panel">
          <p className="hint">No open tasks in this window.</p>
        </section>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => {
            const expanded = openId === task.task_id;
            const members = task.tab_ids
              .map((id) => byId.get(id))
              .filter((tab): tab is TabSnapshot => Boolean(tab));
            return (
              <li
                key={task.task_id}
                className={`task-card ${task.kind}${expanded ? " open" : ""}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  const raw = event.dataTransfer.getData("text/stillopen");
                  if (!raw) {
                    return;
                  }
                  try {
                    const payload = JSON.parse(raw) as { tabId: number; fromId: string };
                    if (payload.fromId === "loose") {
                      onDropLoose(payload.tabId, task.task_id);
                      return;
                    }
                    onMove(payload.tabId, payload.fromId, task.task_id);
                  } catch {
                    /* ignore */
                  }
                }}
              >
                <div className="task-top">
                  <button
                    type="button"
                    className="chevron"
                    aria-expanded={expanded}
                    aria-label={expanded ? "Collapse task" : "Expand task"}
                    onClick={() => setOpenId(expanded ? null : task.task_id)}
                  >
                    {expanded ? "▾" : "▸"}
                  </button>
                  {expanded ? (
                    <TaskTitle
                      label={task.label}
                      locked={busy || task.kind === "protected"}
                      onRename={(label) => onRename(task.task_id, label)}
                    />
                  ) : (
                    <h2 onClick={() => setOpenId(task.task_id)}>{task.label}</h2>
                  )}
                  <span className="task-count">{task.tab_ids.length}</span>
                </div>
                {!expanded ? (
                  <button
                    type="button"
                    className="task-open"
                    onClick={() => setOpenId(task.task_id)}
                  >
                    {task.hosts.slice(0, 3).join(" · ")}
                    {task.hosts.length > 3 ? "…" : ""}
                  </button>
                ) : (
                  <ul className="members">
                    {members.map((tab) => (
                      <li
                        key={tab.tab_id}
                        className={task.kind !== "protected" ? "member drag" : "member"}
                        draggable={task.kind !== "protected"}
                        title={task.kind !== "protected" ? "Drag to another task" : undefined}
                        onDragStart={(event) => {
                          event.dataTransfer.setData(
                            "text/stillopen",
                            JSON.stringify({ tabId: tab.tab_id, fromId: task.task_id }),
                          );
                          event.dataTransfer.effectAllowed = "move";
                        }}
                      >
                        {task.kind !== "protected" ? (
                          <span className="grip" aria-hidden>
                            ⠿
                          </span>
                        ) : null}
                        <span>
                          <span className="title">{tab.title || hostOf(tab.url)}</span>
                          <span className="host">{hostOf(tab.url)}</span>
                        </span>
                        {task.kind !== "protected" ? (
                          <button
                            type="button"
                            className="ghost"
                            aria-label="Remove from task"
                            disabled={busy}
                            onClick={() => onIgnore(task.task_id, tab.tab_id)}
                          >
                            ×
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {task.kind === "protected" ? (
                  <p className="hint">Stays. Never sent to a model.</p>
                ) : (
                  <div className="actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={busy || task.tab_ids.length === 0}
                      onClick={() => onDone(task)}
                    >
                      Done, close!
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <button type="button" className="new-task" disabled={busy} onClick={onNewTask}>
        + New task
      </button>

      {loose.length ? (
        <section className="panel loose">
          <p className="kicker">Not in a task</p>
          <ul className="members">
            {loose.map((tab) => (
              <li
                key={tab.tab_id}
                className="member drag"
                draggable
                title="Drag onto a task"
                onDragStart={(event) => {
                  event.dataTransfer.setData(
                    "text/stillopen",
                    JSON.stringify({ tabId: tab.tab_id, fromId: "loose" }),
                  );
                  event.dataTransfer.effectAllowed = "move";
                }}
              >
                <span className="grip" aria-hidden>
                  ⠿
                </span>
                <span>
                  <span className="title">{tab.title || hostOf(tab.url)}</span>
                  <span className="host">{hostOf(tab.url)}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function TaskTitle({
  label,
  locked,
  onRename,
}: {
  label: string;
  locked: boolean;
  onRename: (label: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);

  useEffect(() => {
    setDraft(label);
  }, [label]);

  if (editing) {
    return (
      <input
        className="rename"
        value={draft}
        autoFocus
        maxLength={48}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft.trim() || label;
          setEditing(false);
          if (next !== label) {
            onRename(next);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            (event.target as HTMLInputElement).blur();
          }
          if (event.key === "Escape") {
            setDraft(label);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <h2
      onDoubleClick={(event) => {
        event.stopPropagation();
        if (!locked) {
          setEditing(true);
        }
      }}
    >
      {label}
    </h2>
  );
}

function Confetti() {
  const colors = ["#1f4b3a", "#c4a35a", "#d45b3a", "#6b8f71", "#f4e3b2", "#2e7d5b"];
  return (
    <div className="confetti" aria-hidden>
      {Array.from({ length: 42 }, (_, i) => (
        <span
          key={i}
          style={{
            left: `${(i * 2.35) % 100}%`,
            width: `${8 + (i % 6)}px`,
            height: `${12 + (i % 5)}px`,
            background: colors[i % colors.length],
            animationDelay: `${i * 28}ms`,
            animationDuration: `${1.2 + (i % 5) * 0.15}s`,
          }}
        />
      ))}
    </div>
  );
}
