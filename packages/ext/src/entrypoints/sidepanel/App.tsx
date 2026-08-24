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
import { getMemory, inferTasks, observeMemory } from "@/lib/api";
import { loadFiledNotes, saveFiledNote } from "@/lib/notes";
import type {
  CloseReply,
  DemoReply,
  RestorePreviewReply,
  SnapshotReply,
  TabChangeMsg,
  UndoReply,
  UpdateNotesReply,
} from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type {
  ChatResponse,
  CloseBatch,
  MemoryDump,
  OpenTask,
  TabSnapshot,
} from "@/lib/schema";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function carryNotes(next: OpenTask[], prev: OpenTask[]): OpenTask[] {
  const byId = new Map(prev.map((task) => [task.task_id, task]));
  return next.map((task) => {
    if (task.notes?.trim()) {
      return task;
    }
    const same = byId.get(task.task_id);
    if (same?.notes?.trim()) {
      return { ...task, notes: same.notes };
    }
    const overlap = prev.find(
      (row) => row.notes?.trim() && row.tab_ids.some((id) => task.tab_ids.includes(id)),
    );
    return overlap ? { ...task, notes: overlap.notes } : task;
  });
}

export function App() {
  const [view, setView] = useState<"work" | "undo" | "memory">("work");
  const [memory, setMemory] = useState<MemoryDump | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [batches, setBatches] = useState<CloseBatch[]>([]);
  const [board, setBoard] = useState<Board>({ tasks: [], ignored: [] });
  const [snapshots, setSnapshots] = useState<TabSnapshot[]>([]);
  const [scanning, setScanning] = useState(true);
  const [hits, setHits] = useState<{ prompt: string; result: ChatResponse } | null>(null);
  const [celebratingId, setCelebratingId] = useState<string | null>(null);
  const boardRef = useRef(board);
  const inferTimer = useRef(0);
  const pruneTimer = useRef(0);
  const celebrateTimer = useRef(0);

  const [closingId, setClosingId] = useState<string | null>(null);
  const [farewell, setFarewell] = useState<OpenTask | null>(null);
  const celebratingRef = useRef<string | null>(null);
  const closingRef = useRef<string | null>(null);
  celebratingRef.current = celebratingId;
  closingRef.current = closingId;

  boardRef.current = board;

  useEffect(() => {
    void refreshUndo();
    void loadMemory().then(() => scan(true));
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
    if (!reply.ok) {
      return;
    }
    const filed = await loadFiledNotes();
    const used = new Set<string>();
    setBatches(
      reply.batches.map((batch) => {
        if (batch.notes?.trim()) {
          return batch;
        }
        const match = filed.find((row) => row.label === batch.label && !used.has(row.id));
        if (!match) {
          return batch;
        }
        used.add(match.id);
        return { ...batch, notes: match.notes };
      }),
    );
  }

  async function commit(next: Board) {
    boardRef.current = next;
    setBoard(next);
    await saveBoard(next);
  }

  async function dismissTask(taskId: string) {
    const current = boardRef.current;
    if (!current.tasks.some((task) => task.task_id === taskId)) {
      return;
    }
    await commit({
      ...current,
      tasks: current.tasks.filter((task) => task.task_id !== taskId),
    });
  }

  async function localPrune() {
    if (celebratingRef.current || closingRef.current) {
      return;
    }
    const reply = await send<SnapshotReply>({ type: "SNAPSHOT" });
    if (!reply.ok) {
      return;
    }
    setSnapshots(reply.tabs);
    await commit(pruneBoard(boardRef.current, reply.tabs));
  }

  async function scan(full: boolean) {
    if ((celebratingRef.current || closingRef.current) && !full) {
      return;
    }
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
        existing: full
          ? pruned.tasks.filter(
              (task) => task.user_locked || task.kind === "protected" || Boolean(task.notes?.trim()),
            )
          : pruned.tasks,
        ignoredUrls: pruned.ignored,
        fast: !full,
      });
      await commit({ tasks: carryNotes(inferred, pruned.tasks), ignored: pruned.ignored });
    } catch (error) {
      setNotice(String(error));
    } finally {
      setScanning(false);
    }
  }

  function celebrate(taskId: string) {
    setCelebratingId(taskId);
    window.clearTimeout(celebrateTimer.current);
    celebrateTimer.current = window.setTimeout(() => {
      celebratingRef.current = null;
      closingRef.current = null;
      setCelebratingId(null);
      setClosingId(null);
      setFarewell(null);
      setHits(null);
      void localPrune();
      void loadMemory();
    }, 2100);
  }

  async function closeTabs(
    tabIds: number[],
    label: string,
    notes = "",
  ): Promise<{ closed: number; batchId: string | null }> {
    const reply = await send<CloseReply>({ type: "APPLY_CLOSE", tabIds, label, notes });
    if (!reply.ok) {
      throw new Error(reply.error);
    }
    if (reply.closed > 0) {
      await refreshUndo();
    }
    return { closed: reply.closed, batchId: reply.batch?.batch_id ?? null };
  }

  async function onDone(task: OpenTask) {
    setClosingId(task.task_id);
    celebrate(task.task_id);
    try {
      const latest = boardRef.current.tasks.find((row) => row.task_id === task.task_id) ?? task;
      const note = (latest.notes ?? task.notes ?? "").trim();
      const tabs = snapshots.filter((tab) => latest.tab_ids.includes(tab.tab_id));
      if (tabs.length === 0) {
        throw new Error("Those tabs are gone.");
      }
      await closeTabs(latest.tab_ids, latest.label, note);
      setSnapshots((live) => live.filter((tab) => !latest.tab_ids.includes(tab.tab_id)));
      setFarewell(latest);
      await dismissTask(latest.task_id);
      if (note) {
        await saveFiledNote({ ...latest, notes: note });
      }
      void observeMemory({
        kind: "stillopen_close",
        host: latest.hosts[0] ?? "",
        title: latest.label,
        source: "task",
      });
      setNotice(note ? `Closed “${latest.label}”. Note saved.` : `Closed “${latest.label}”.`);
    } catch (error) {
      window.clearTimeout(celebrateTimer.current);
      celebratingRef.current = null;
      closingRef.current = null;
      setCelebratingId(null);
      setFarewell(null);
      setNotice(String(error));
    } finally {
      setClosingId(null);
    }
  }

  async function onChatClose(tabIds: number[], label: string) {
    setBusy(true);
    const hit = board.tasks.find((task) => tabIds.some((id) => task.tab_ids.includes(id)));
    celebrate(hit?.task_id ?? "chat");
    try {
      await closeTabs(tabIds, label || "Ask");
      if (hit) {
        setSnapshots((live) => live.filter((tab) => !tabIds.includes(tab.tab_id)));
        setFarewell(hit);
        await dismissTask(hit.task_id);
      }
    } catch (error) {
      window.clearTimeout(celebrateTimer.current);
      celebratingRef.current = null;
      setCelebratingId(null);
      setFarewell(null);
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

  function onNotes(batchId: string, notes: string) {
    setBatches((prev) =>
      prev.map((batch) => (batch.batch_id === batchId ? { ...batch, notes } : batch)),
    );
    void send<UpdateNotesReply>({ type: "UPDATE_BATCH_NOTES", batchId, notes });
  }

  const loose = looseTabs(snapshots, board);
  const shownTasks =
    farewell && !board.tasks.some((task) => task.task_id === farewell.task_id)
      ? [farewell, ...board.tasks]
      : board.tasks;

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
          Finished{batches.length ? ` (${batches.length})` : ""}
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
        <UndoView
          batches={batches}
          busy={busy}
          onRestore={(id) => void onRestore(id)}
          onNotes={onNotes}
        />
      ) : (
        <>
          <ChatBox
            busy={busy}
            tasks={board.tasks}
            onApplied={(result, prompt) => {
              if (result.wants_close || result.matches.length > 0) {
                setHits({ prompt, result });
                return;
              }
              setHits(null);
              void loadMemory();
            }}
          />
          {hits ? (
            <ChatHits
              key={hits.prompt}
              label={hits.result.label || hits.prompt}
              matches={hits.result.matches}
              busy={busy}
              celebrating={celebratingId === "chat"}
              onDismiss={() => setHits(null)}
              onClose={(ids) => void onChatClose(ids, hits.result.label || hits.prompt)}
            />
          ) : null}
          <Workbench
            tasks={shownTasks}
            live={snapshots}
            loose={loose}
            scanning={scanning}
            busy={busy}
            closingId={closingId}
            celebratingId={celebratingId}
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
            onNotes={(taskId, notes) => {
              void commit({
                ...board,
                tasks: board.tasks.map((task) =>
                  task.task_id === taskId ? { ...task, notes, user_locked: true } : task,
                ),
              });
            }}
            onIgnore={(taskId, tabId) => void commit(ignoreTab(board, taskId, tabId, snapshots))}
            onMove={(tabId, fromId, toId) => void commit(moveTab(board, tabId, fromId, toId, snapshots))}
            onDropLoose={(tabId, toId) => void commit(dropLoose(board, tabId, toId, snapshots))}
          />
          <p className="foot">Closes are real. Notes stay in Finished.</p>
        </>
      )}
    </main>
  );
}
