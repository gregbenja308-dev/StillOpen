import { useEffect, useState } from "react";

import { MemoryView } from "./MemoryView";
import { UndoView } from "./UndoView";
import { Workbench } from "./Workbench";
import {
  createPlan,
  getMemory,
  googleAuthStatus,
  googleAuthUrl,
  inferTasks,
  observeMemory,
  runPlan,
} from "@/lib/api";
import type { CloseReply, DemoReply, SnapshotReply, UndoPreviewReply, UndoReply } from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type { MemoryDump, OpenTask, RunResponse, TabSnapshot, UndoRow } from "@/lib/schema";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function App() {
  const [view, setView] = useState<"work" | "undo" | "memory">("work");
  const [memory, setMemory] = useState<MemoryDump | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [undoRows, setUndoRows] = useState<UndoRow[]>([]);
  const [tasks, setTasks] = useState<OpenTask[]>([]);
  const [snapshots, setSnapshots] = useState<TabSnapshot[]>([]);
  const [scanning, setScanning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResponse | null>(null);
  const [googleOk, setGoogleOk] = useState<{ connected: boolean; configured: boolean } | null>(null);

  useEffect(() => {
    void refreshUndo();
    void loadMemory().then(() => scan());
    void googleAuthStatus()
      .then(setGoogleOk)
      .catch(() => setGoogleOk(null));
  }, []);

  useEffect(() => {
    if (view !== "memory") {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void loadMemory();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [view]);

  async function loadMemory(): Promise<MemoryDump | null> {
    try {
      const dump = await getMemory();
      setMemory(dump);
      return dump;
    } catch {
      return null;
    }
  }

  async function refreshUndo() {
    const reply = await send<UndoPreviewReply>({ type: "UNDO_PREVIEW" });
    if (reply.ok) {
      setUndoRows(reply.rows);
    }
  }

  async function scan() {
    setScanning(true);
    try {
      const reply = await send<SnapshotReply>({ type: "SNAPSHOT" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      setSnapshots(reply.tabs);
      const dump = memory ?? (await loadMemory());
      const cutoff = dump?.profile.stale_cutoff_days ?? 7;
      setTasks(await inferTasks(reply.tabs, cutoff));
    } catch (error) {
      setNotice(String(error));
    } finally {
      setScanning(false);
    }
  }

  async function closeTabs(tabIds: number[]): Promise<number> {
    const reply = await send<CloseReply>({ type: "APPLY_CLOSE", tabIds });
    if (!reply.ok) {
      throw new Error(reply.error);
    }
    if (reply.closed > 0) {
      setUndoRows(reply.rows);
    }
    return reply.closed;
  }

  async function onKeepGoing(task: OpenTask) {
    setBusy(true);
    try {
      for (const host of task.hosts) {
        await observeMemory({ kind: "keep", host, title: task.label, source: "task" });
      }
      setNotice(`Keeping “${task.label}”.`);
      await loadMemory();
    } finally {
      setBusy(false);
    }
  }

  async function onDone(task: OpenTask) {
    setBusy(true);
    try {
      const tabs = snapshots.filter((tab) => task.tab_ids.includes(tab.tab_id));
      if (tabs.length === 0) {
        throw new Error("Those tabs are gone. Refresh.");
      }
      if (task.kind === "durable") {
        const plan = await createPlan(task.label, tabs, { forceFile: true });
        const run = await runPlan(
          plan.plan_id,
          tabs.map((tab) => ({ tab_id: tab.tab_id, checked: true })),
        );
        setLastRun(run);
        if (!run.report.artifacts_ok) {
          setNotice("Couldn’t save the work — tabs stay open.");
          return;
        }
        const closeIds = run.apply.close_tab_ids.filter((id) => task.tab_ids.includes(id));
        const closed = closeIds.length ? await closeTabs(closeIds) : 0;
        setView("undo");
        setNotice(
          closed > 0 ? `Saved, then closed ${plural(closed, "tab")}.` : "Saved. Nothing to close.",
        );
      } else {
        const closed = await closeTabs(task.tab_ids);
        setView("undo");
        setNotice(closed > 0 ? `Closed ${plural(closed, "tab")}.` : "Nothing to close.");
      }
      await scan();
      await loadMemory();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onDemo() {
    setBusy(true);
    try {
      const reply = await send<DemoReply>({ type: "OPEN_DEMO" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      setNotice(reply.opened === 0 ? "Demo tabs are already here." : "Demo window ready.");
      await scan();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onUndo() {
    setBusy(true);
    try {
      const reply = await send<UndoReply>({ type: "UNDO" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      for (const row of undoRows) {
        const host = (() => {
          try {
            return new URL(row.url).hostname.replace(/^www\./, "");
          } catch {
            return "";
          }
        })();
        if (host) {
          await observeMemory({ kind: "undo", host, title: row.title, source: "undo" });
        }
      }
      setUndoRows([]);
      setNotice(`Restored ${plural(reply.restored, "tab")}.`);
      await scan();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <nav className="nav" aria-label="Still Open views">
        <button type="button" className={view === "work" ? "on" : undefined} onClick={() => setView("work")}>
          Work
        </button>
        <button
          type="button"
          className={view === "undo" ? "on" : undefined}
          onClick={() => {
            setView("undo");
            void refreshUndo();
          }}
        >
          Restore{undoRows.length ? ` (${undoRows.length})` : ""}
        </button>
        <button
          type="button"
          className={view === "memory" ? "on" : undefined}
          onClick={() => {
            setView("memory");
            void loadMemory();
          }}
        >
          Memory
        </button>
      </nav>

      {notice ? (
        <p className="status" role="status">
          {notice}
        </p>
      ) : null}

      {view === "memory" ? (
        <MemoryView dump={memory} />
      ) : view === "undo" ? (
        <UndoView rows={undoRows} lastRun={lastRun} busy={busy} onRestore={() => void onUndo()} />
      ) : (
        <>
          <Workbench
            tasks={tasks}
            scanning={scanning}
            busy={busy}
            onRefresh={() => void scan()}
            onDemo={() => void onDemo()}
            onDone={(task) => void onDone(task)}
            onKeepGoing={(task) => void onKeepGoing(task)}
          />
          <p className="foot">
            {googleOk?.connected
              ? "Google connected."
              : googleOk?.configured
                ? "Connect Google to save durable tasks."
                : "Closes are real."}{" "}
            {googleOk?.configured && !googleOk.connected ? (
              <button
                type="button"
                className="linkish"
                onClick={() => void googleAuthUrl().then((url) => chrome.tabs.create({ url }))}
              >
                Connect
              </button>
            ) : null}
          </p>
        </>
      )}
    </main>
  );
}
