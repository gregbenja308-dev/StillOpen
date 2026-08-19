import { useEffect, useRef, useState } from "react";

import { ChatBox } from "./ChatBox";
import { ChatHits } from "./ChatHits";
import { MemoryView } from "./MemoryView";
import { UndoView } from "./UndoView";
import { Workbench } from "./Workbench";
import {
  dropLoose,
  ignoreTab,
  loadBoard,
  looseTabs,
  moveTab,
  newTask,
  pruneBoard,
  saveBoard,
  type Board,
} from "@/lib/board";
import {
  createPlan,
  getMemory,
  googleAuthStatus,
  googleAuthUrl,
  inferTasks,
  observeMemory,
  runPlan,
} from "@/lib/api";
import type {
  CloseReply,
  DemoReply,
  RestorePreviewReply,
  SnapshotReply,
  TabChangeMsg,
  UndoReply,
} from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type {
  ChatResponse,
  CloseBatch,
  MemoryDump,
  OpenTask,
  RunResponse,
  TabSnapshot,
} from "@/lib/schema";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function App() {
  const [view, setView] = useState<"work" | "undo" | "memory">("work");
  const [memory, setMemory] = useState<MemoryDump | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [batches, setBatches] = useState<CloseBatch[]>([]);
  const [board, setBoard] = useState<Board>({ tasks: [], ignored: [] });
  const [snapshots, setSnapshots] = useState<TabSnapshot[]>([]);
  const [scanning, setScanning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResponse | null>(null);
  const [googleOk, setGoogleOk] = useState<{ connected: boolean; configured: boolean } | null>(null);
  const [hits, setHits] = useState<{ prompt: string; result: ChatResponse } | null>(null);
  const [burst, setBurst] = useState(false);
  const boardRef = useRef(board);
  const inferTimer = useRef(0);
  const pruneTimer = useRef(0);

  boardRef.current = board;

  useEffect(() => {
    void refreshUndo();
    void loadMemory().then(() => scan(true));
    void googleAuthStatus()
      .then(setGoogleOk)
      .catch(() => setGoogleOk(null));
  }, []);

  useEffect(() => {
    const onMsg = (message: TabChangeMsg) => {
      if (message.type !== "TABS_CHANGED") {
        return;
      }
      if (message.reason === "removed") {
        window.clearTimeout(pruneTimer.current);
        pruneTimer.current = window.setTimeout(() => {
          void localPrune();
        }, 80);
        return;
      }
      window.clearTimeout(inferTimer.current);
      inferTimer.current = window.setTimeout(() => {
        void scan(false);
      }, 1200);
    };
    chrome.runtime.onMessage.addListener(onMsg);
    return () => chrome.runtime.onMessage.removeListener(onMsg);
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
    const reply = await send<RestorePreviewReply>({ type: "RESTORE_PREVIEW" });
    if (reply.ok) {
      setBatches(reply.batches);
    }
  }

  async function commit(next: Board) {
    setBoard(next);
    await saveBoard(next);
  }

  async function localPrune() {
    const reply = await send<SnapshotReply>({ type: "SNAPSHOT" });
    if (!reply.ok) {
      return;
    }
    setSnapshots(reply.tabs);
    await commit(pruneBoard(boardRef.current, reply.tabs));
  }

  async function scan(full: boolean) {
    setScanning(true);
    try {
      const reply = await send<SnapshotReply>({ type: "SNAPSHOT" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      setSnapshots(reply.tabs);
      const saved = full && boardRef.current.tasks.length === 0 ? await loadBoard() : boardRef.current;
      const pruned = pruneBoard(saved, reply.tabs);
      const dump = memory ?? (await loadMemory());
      const cutoff = dump?.profile.stale_cutoff_days ?? 7;
      if (reply.tabs.length === 0) {
        await commit(pruned);
        return;
      }
      const inferred = await inferTasks(reply.tabs, {
        cutoffDays: cutoff,
        existing: pruned.tasks.filter(
          (task) => task.user_locked || task.kind === "protected",
        ),
        ignoredUrls: pruned.ignored,
      });
      await commit({ tasks: inferred, ignored: pruned.ignored });
    } catch (error) {
      setNotice(String(error));
    } finally {
      setScanning(false);
    }
  }

  async function closeTabs(tabIds: number[], label: string): Promise<number> {
    const reply = await send<CloseReply>({ type: "APPLY_CLOSE", tabIds, label });
    if (!reply.ok) {
      throw new Error(reply.error);
    }
    if (reply.closed > 0) {
      await refreshUndo();
    }
    return reply.closed;
  }

  async function onDone(task: OpenTask) {
    setBusy(true);
    try {
      const tabs = snapshots.filter((tab) => task.tab_ids.includes(tab.tab_id));
      if (tabs.length === 0) {
        throw new Error("Those tabs are gone.");
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
        await closeTabs(closeIds.length ? closeIds : task.tab_ids, task.label);
      } else {
        await closeTabs(task.tab_ids, task.label);
      }
      await observeMemory({
        kind: "stillopen_close",
        host: task.hosts[0] ?? "",
        title: task.label,
        source: "task",
      });
      setBurst(true);
      window.setTimeout(() => setBurst(false), 900);
      setNotice(`Closed “${task.label}”.`);
      await scan(false);
      await loadMemory();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onChatClose(tabIds: number[], label: string) {
    setBusy(true);
    try {
      await closeTabs(tabIds, label || "Ask");
      setHits(null);
      setBurst(true);
      window.setTimeout(() => setBurst(false), 900);
      await scan(false);
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
      await scan(true);
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onRestore(batchId: string) {
    setBusy(true);
    try {
      const batch = batches.find((row) => row.batch_id === batchId);
      const reply = await send<UndoReply>({ type: "RESTORE_BATCH", batchId });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      for (const row of batch?.rows ?? []) {
        try {
          await observeMemory({
            kind: "undo",
            host: new URL(row.url).hostname.replace(/^www\./, ""),
            title: row.title,
            source: "undo",
          });
        } catch {
          /* ignore bad urls */
        }
      }
      setNotice(`Restored ${plural(reply.restored, "tab")}.`);
      await refreshUndo();
      await scan(false);
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  const loose = looseTabs(snapshots, board);

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
          Restore{batches.length ? ` (${batches.length})` : ""}
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
        <UndoView batches={batches} lastRun={lastRun} busy={busy} onRestore={(id) => void onRestore(id)} />
      ) : (
        <>
          <ChatBox
            busy={busy}
            onApplied={(result, prompt) => {
              if (result.wants_close) {
                setHits({ prompt, result });
                return;
              }
              void loadMemory();
            }}
          />
          {hits ? (
            <ChatHits
              label={hits.result.label || hits.prompt}
              matches={hits.result.matches}
              busy={busy}
              onDismiss={() => setHits(null)}
              onClose={(ids) => void onChatClose(ids, hits.result.label || hits.prompt)}
            />
          ) : null}
          <Workbench
            tasks={board.tasks}
            live={snapshots}
            loose={loose}
            scanning={scanning}
            busy={busy}
            burst={burst}
            onRefresh={() => void scan(true)}
            onDemo={() => void onDemo()}
            onNewTask={() => void commit({ ...board, tasks: [newTask(), ...board.tasks] })}
            onDone={(task) => void onDone(task)}
            onRename={(taskId, label) => {
              void commit({
                ...board,
                tasks: board.tasks.map((task) =>
                  task.task_id === taskId ? { ...task, label, user_locked: true } : task,
                ),
              });
            }}
            onIgnore={(taskId, tabId) => void commit(ignoreTab(board, taskId, tabId, snapshots))}
            onMove={(tabId, fromId, toId) => void commit(moveTab(board, tabId, fromId, toId, snapshots))}
            onDropLoose={(tabId, toId) => void commit(dropLoose(board, tabId, toId, snapshots))}
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
