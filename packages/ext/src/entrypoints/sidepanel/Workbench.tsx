import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { OpenTask, TabSnapshot } from "@/lib/schema";
import { hostOf } from "@/lib/stale";

export function Workbench({
  tasks,
  live,
  loose,
  scanning,
  busy,
  closingId,
  celebratingId,
  onRefresh,
  onDemo,
  onNewTask,
  onDone,
  onStillGoing,
  onRename,
  onNotes,
  onIgnore,
  onMove,
  onDropLoose,
}: {
  tasks: OpenTask[];
  live: TabSnapshot[];
  loose: TabSnapshot[];
  scanning: boolean;
  busy: boolean;
  closingId: string | null;
  celebratingId: string | null;
  onRefresh: () => void;
  onDemo: () => void;
  onNewTask: () => void;
  onDone: (task: OpenTask) => void;
  onStillGoing: (task: OpenTask) => void;
  onRename: (taskId: string, label: string) => void;
  onNotes: (taskId: string, notes: string) => void;
  onIgnore: (taskId: string, tabId: number) => void;
  onMove: (tabId: number, fromId: string, toId: string) => void;
  onDropLoose: (tabId: number, toId: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const noteDrafts = useRef<Record<string, string>>({});
  const byId = new Map(live.map((tab) => [tab.tab_id, tab]));

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
              Demo Seed
            </button>
            <button type="button" disabled={busy || scanning} onClick={onRefresh}>
              {scanning ? "…" : "Rescan"}
            </button>
          </div>
        </div>
      </header>

      {scanning && tasks.length === 0 ? (
        <section className="panel scanning" aria-live="polite" aria-busy="true">
          <span className="spinner" aria-hidden />
          <p className="scanning-copy">Looking for unfinished tasks in this window</p>
        </section>
      ) : tasks.length === 0 ? (
        <section className="panel">
          <p className="hint">No open tasks in this window.</p>
        </section>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => {
            const expanded = openId === task.task_id;
            const closing = closingId === task.task_id || celebratingId === task.task_id;
            const members = task.tab_ids
              .map((id) => byId.get(id))
              .filter((tab): tab is TabSnapshot => Boolean(tab));
            return (
              <li
                key={task.task_id}
                className={`task-card ${task.kind}${expanded ? " open" : ""}${closing ? " closing" : ""}`}
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
                {celebratingId === task.task_id ? <Confetti /> : null}
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
                    {task.notes?.trim() ? ` · ${task.notes.trim().slice(0, 48)}` : ""}
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
                {expanded && task.kind !== "protected" && !closing ? (
                  <TaskNotes
                    notes={task.notes ?? ""}
                    onSave={(notes) => {
                      noteDrafts.current[task.task_id] = notes;
                      onNotes(task.task_id, notes);
                    }}
                  />
                ) : null}
                {task.kind === "protected" ? (
                  <p className="protect-why">
                    Bank, health, government, and login tabs stay on this laptop.
                    They are never sent to a model.
                  </p>
                ) : closing ? (
                  <div className="closing-banner" aria-live="polite" aria-busy="true">
                    <span className="spinner" aria-hidden />
                    <p className="scanning-copy">Closing these tabs…</p>
                  </div>
                ) : (
                  <div className="actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={Boolean(closingId) || task.tab_ids.length === 0}
                      onClick={() =>
                        onDone({
                          ...task,
                          notes: noteDrafts.current[task.task_id] ?? task.notes ?? "",
                        })
                      }
                    >
                      Done, close!
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      disabled={busy || Boolean(closingId) || task.tab_ids.length === 0}
                      title="Track these tabs; ping me when they change"
                      onClick={() =>
                        onStillGoing({
                          ...task,
                          notes: noteDrafts.current[task.task_id] ?? task.notes ?? "",
                        })
                      }
                    >
                      Still going
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

function TaskNotes({ notes, onSave }: { notes: string; onSave: (notes: string) => void }) {
  const [draft, setDraft] = useState(notes);

  useEffect(() => {
    setDraft(notes);
  }, [notes]);

  return (
    <label className="task-notes">
      <span className="kicker">Notes</span>
      <textarea
        value={draft}
        maxLength={4000}
        rows={3}
        placeholder="What should survive when these tabs close?"
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          onSave(next);
        }}
        onBlur={() => {
          if (draft !== notes) {
            onSave(draft);
          }
        }}
      />
    </label>
  );
}

export function Confetti() {
  const colors = ["#1f4b3a", "#c4a35a", "#d45b3a", "#6b8f71", "#f4e3b2"];
  return (
    <div className="confetti" aria-hidden>
      {Array.from({ length: 22 }, (_, i) => {
        const angle = (i / 22) * Math.PI * 2 + (i % 4) * 0.12;
        const dist = 44 + (i % 6) * 10;
        return (
          <i
            key={i}
            className={i % 3 === 0 ? "tick" : "dot"}
            style={
              {
                "--x": `${Math.round(Math.cos(angle) * dist)}px`,
                "--y": `${Math.round(Math.sin(angle) * dist * 0.78 - 8)}px`,
                "--r": `${(i * 28) % 140 - 70}deg`,
                "--s": `${7 + (i % 4)}px`,
                "--d": `${(i % 6) * 40}ms`,
                background: colors[i % colors.length],
              } as CSSProperties
            }
          />
        );
      })}
    </div>
  );
}
