import { useEffect, useState } from "react";

import { ChatBox } from "./ChatBox";
import { ChatHits } from "./ChatHits";
import { MemoryView } from "./MemoryView";
import { UndoView } from "./UndoView";
import {
  categorizeTabs,
  createPlan,
  getMemory,
  googleAuthStatus,
  googleAuthUrl,
  observeMemory,
  runPlan,
  scheduleClose,
} from "@/lib/api";
import { dumpFromChat } from "@/lib/memory";
import { closeOkHosts, keepHosts } from "@/lib/memory";
import { DEMO_COMMAND } from "@/lib/demo";
import type {
  CloseReply,
  DemoReply,
  ScanReply,
  ScheduleReply,
  SnapshotReply,
  UndoPreviewReply,
  UndoReply,
} from "@/lib/messaging";
import { send } from "@/lib/messaging";
import type { ChatResponse, MatchedTab, MemoryDump, RunResponse, TabGroup, UndoRow } from "@/lib/schema";
import { CUTOFF_CHOICES, setCutoffDays } from "@/lib/settings";
import { findStaleTabs, hostMatches, hostOf, type StaleTab } from "@/lib/stale";

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function daysLabel(days: number): string {
  return days === 1 ? "1 day" : `${days} days`;
}

export function App() {
  const [view, setView] = useState<"work" | "undo" | "memory">("work");
  const [memory, setMemory] = useState<MemoryDump | null>(null);
  const [chatReply, setChatReply] = useState("");
  const [chatHits, setChatHits] = useState<{
    prompt: string;
    label: string;
    matches: MatchedTab[];
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [undoRows, setUndoRows] = useState<UndoRow[]>([]);
  const [stale, setStale] = useState<StaleTab[]>([]);
  const [staleGroups, setStaleGroups] = useState<TabGroup[]>([]);
  const [staleChecked, setStaleChecked] = useState<Record<number, boolean>>({});
  const [cutoffDays, setCutoff] = useState(7);
  const [scanning, setScanning] = useState(false);
  const [lastRun, setLastRun] = useState<RunResponse | null>(null);
  const [googleOk, setGoogleOk] = useState<{ connected: boolean; configured: boolean } | null>(null);

  const staleSelected = stale.filter((row) => staleChecked[row.tab.tab_id]);
  const allStaleSelected = stale.length > 0 && staleSelected.length === stale.length;
  const learnedClose = closeOkHosts(memory?.profile);

  useEffect(() => {
    void refreshUndo();
    void loadMemory().then((dump) => scanTabs(dump));
    void googleAuthStatus().then(setGoogleOk).catch(() => setGoogleOk(null));
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
      setCutoff(dump.profile.stale_cutoff_days);
      await setCutoffDays(dump.profile.stale_cutoff_days);
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

  async function scanTabs(dump = memory) {
    setScanning(true);
    try {
      const live = dump ?? (await loadMemory());
      const reply = await send<ScanReply>({ type: "SCAN" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      const cutoff = live?.profile.stale_cutoff_days ?? reply.cutoffDays;
      setCutoff(cutoff);
      const next = findStaleTabs(reply.tabs, cutoff, { keepHosts: keepHosts(live?.profile) });
      setStale(next);
      setStaleChecked(Object.fromEntries(next.map((row) => [row.tab.tab_id, true])));
      if (next.length === 0) {
        setStaleGroups([]);
      } else {
        try {
          setStaleGroups(await categorizeTabs(next.map((row) => row.tab)));
        } catch {
          setStaleGroups([{ title: "Unused tabs", tab_ids: next.map((row) => row.tab.tab_id) }]);
        }
      }
    } catch (error) {
      setNotice(String(error));
    } finally {
      setScanning(false);
    }
  }

  async function applyMemory(next: MemoryDump, reply?: string) {
    setMemory(next);
    setCutoff(next.profile.stale_cutoff_days);
    await setCutoffDays(next.profile.stale_cutoff_days);
    if (reply) {
      setChatReply(reply);
      setNotice(reply);
    }
    await scanTabs(next);
  }

  async function applyChat(result: ChatResponse, message: string) {
    const dump = dumpFromChat(result.profile, result.storage);
    await applyMemory(dump, result.reply);
    if (result.wants_close) {
      setChatHits({ prompt: message, label: result.label, matches: result.matches });
      setView("work");
    }
  }

  async function onCutoff(days: number) {
    setCutoff(days);
    await setCutoffDays(days);
    const dump = await observeMemory({
      kind: "keep",
      source: "sweep",
      stale_cutoff_days: days,
      title: `unused cutoff ${days}`,
    });
    if (dump) {
      setMemory(dump);
    }
    await scanTabs(dump ?? memory);
  }

  async function onFileHits(tabIds: number[]) {
    if (!chatHits) {
      return;
    }
    setBusy(true);
    try {
      const snap = await send<SnapshotReply>({ type: "SNAPSHOT" });
      if (!snap.ok) {
        throw new Error(snap.error);
      }
      const tabs = snap.tabs.filter((tab) => tabIds.includes(tab.tab_id));
      if (tabs.length === 0) {
        throw new Error("Those tabs are gone. Re-scan and ask again.");
      }
      const plan = await createPlan(chatHits.prompt, tabs, { forceFile: true });
      const run = await runPlan(
        plan.plan_id,
        tabs.map((tab) => ({ tab_id: tab.tab_id, checked: true })),
      );
      setLastRun(run);
      if (!run.report.artifacts_ok) {
        setNotice(
          `File failed — tabs stay open. ${run.report.notes || "Clerk/Docs did not land."}`,
        );
        return;
      }
      const closeIds = run.apply.close_tab_ids.filter((id) => tabIds.includes(id));
      const closed = closeIds.length > 0 ? await closeTabs(closeIds) : 0;
      const doc = run.artifacts.find((row) => row.kind === "doc") ?? run.artifacts[0];
      setChatHits(null);
      setView("undo");
      setNotice(
        closed > 0
          ? `Filed, then closed ${plural(closed, "tab")}. Restore is on the next tab.`
          : "Filed into Google. Nothing was eligible to close.",
      );
      if (doc?.url) {
        setNotice((prev) => `${prev} ${doc.title || "Doc"}: ${doc.url}`);
      }
      await scanTabs(await loadMemory());
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onCloseHits(tabIds: number[]) {
    setBusy(true);
    try {
      const closed = await closeTabs(tabIds);
      setChatHits(null);
      if (closed > 0) {
        setView("undo");
      }
      setNotice(
        closed > 0
          ? `Closed ${plural(closed, "tab")} from chat. Restore is on the next tab.`
          : "Nothing was eligible to close.",
      );
      await scanTabs(await loadMemory());
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onScheduleHits(tabIds: number[], whenMs: number) {
    if (!chatHits) {
      return;
    }
    setBusy(true);
    try {
      const selected = chatHits.matches.filter((row) => tabIds.includes(row.tab_id));
      const scheduleId = crypto.randomUUID().replaceAll("-", "").slice(0, 26);
      await scheduleClose({
        prompt: chatHits.prompt,
        label: chatHits.label,
        run_at: new Date(whenMs).toISOString(),
        matches: selected,
        schedule_id: scheduleId,
      });
      const reply = await send<ScheduleReply>({
        type: "SCHEDULE_CLOSE",
        scheduleId,
        whenMs,
        tabIds,
      });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      setChatHits(null);
      setNotice(`Scheduled ${plural(selected.length, "tab")} for ${new Date(whenMs).toLocaleString()}.`);
      await loadMemory();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onOpenDemo() {
    setBusy(true);
    try {
      const reply = await send<DemoReply>({ type: "OPEN_DEMO" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      if (reply.opened === 0) {
        setNotice(`Demo tabs are already here. Ask: “${DEMO_COMMAND}.”`);
      } else {
        setNotice(
          `Opened ${plural(reply.opened, "demo tab")}${
            reply.already ? ` (${reply.already} already here)` : ""
          }. Ask: “${DEMO_COMMAND}.”`,
        );
      }
      await scanTabs(await loadMemory());
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
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

  async function onCloseStale() {
    if (staleSelected.length === 0) {
      return;
    }
    setBusy(true);
    try {
      const skipped = stale.filter((row) => !staleChecked[row.tab.tab_id]);
      for (const row of skipped) {
        await observeMemory({
          kind: "keep",
          host: row.host,
          title: row.tab.title,
          source: "stale",
        });
      }
      const closed = await closeTabs(staleSelected.map((row) => row.tab.tab_id));
      if (closed > 0) {
        setView("undo");
      }
      setNotice(
        closed > 0
          ? `Closed ${plural(closed, "unused tab")}. Restore lists every site that will reopen.`
          : "Nothing was eligible to close.",
      );
      await scanTabs(await loadMemory());
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function onUndo() {
    setBusy(true);
    try {
      const hosts = undoRows.map((row) => ({ host: hostOf(row.url), title: row.title }));
      const reply = await send<UndoReply>({ type: "UNDO" });
      if (!reply.ok) {
        throw new Error(reply.error);
      }
      for (const row of hosts) {
        await observeMemory({ kind: "undo", host: row.host, title: row.title, source: "undo" });
      }
      setUndoRows([]);
      setNotice(`Restored ${plural(reply.restored, "tab")}. Those hosts will stay next time.`);
      await scanTabs(await loadMemory());
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
          Workbench
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
        <MemoryView dump={memory} onChat={(result, message) => void applyChat(result, message)} />
      ) : view === "undo" ? (
        <UndoView
          rows={undoRows}
          lastRun={lastRun}
          busy={busy}
          onRestore={() => void onUndo()}
        />
      ) : (
        <>
          <header>
            <div className="panel-head">
              <div>
                <h1>Still Open</h1>
                <p className="lede">An open tab is unfinished work. File it, or let it go — on purpose.</p>
              </div>
              <button type="button" disabled={busy} onClick={() => void onOpenDemo()}>
                Open demo tabs
              </button>
            </div>
          </header>

          <div className="ask-stack">
            <section className="panel ask-panel">
              <p className="kicker">Ask, then close</p>
              <h2>What should we close?</h2>
              <p className="hint">
                File writes the listings into a Google Doc, then closes. Close now just kills the
                tab. Chase stays off the model.
              </p>
              <ChatBox onApplied={(result, message) => void applyChat(result, message)} />
              {chatReply && !chatHits ? <p className="status">{chatReply}</p> : null}
            </section>
            {chatHits ? (
              <>
                <div className="ask-arrow" aria-hidden="true">
                  <span className="ask-arrow-line" />
                  <span className="ask-arrow-head">▼</span>
                </div>
                <ChatHits
                  key={chatHits.matches.map((row) => row.tab_id).join("-") || chatHits.label}
                  prompt={chatHits.prompt}
                  label={chatHits.label}
                  matches={chatHits.matches}
                  busy={busy}
                  onCloseNow={(ids) => void onCloseHits(ids)}
                  onFileThenClose={(ids) => void onFileHits(ids)}
                  onSchedule={(ids, whenMs) => void onScheduleHits(ids, whenMs)}
                  onDismiss={() => setChatHits(null)}
                />
              </>
            ) : null}
          </div>

          <section className="panel" aria-labelledby="stale-heading">
            <div className="panel-head">
              <div>
                <p className="kicker">Daily sweep</p>
                <h2 id="stale-heading">
                  {stale.length === 0
                    ? "No neglected tabs"
                    : `You haven't opened ${plural(stale.length, "tab")} in ${daysLabel(cutoffDays)}`}
                </h2>
              </div>
              <button type="button" disabled={busy || scanning} onClick={() => void scanTabs()}>
                {scanning ? "Scanning…" : "Re-scan tabs"}
              </button>
            </div>
            {stale.length > 0 ? (
              <>
                <p className="prompt">
                  Close the ones you do not need? Sites you asked to keep are hidden. Select all, or only some.
                </p>
                <div className="toolbar">
                  <fieldset className="cutoff">
                    <legend>Unused for</legend>
                    {CUTOFF_CHOICES.map((days) => (
                      <label key={days} className={cutoffDays === days ? "on" : undefined}>
                        <input
                          type="radio"
                          name="cutoff"
                          checked={cutoffDays === days}
                          onChange={() => void onCutoff(days)}
                        />
                        {daysLabel(days)}
                      </label>
                    ))}
                    {CUTOFF_CHOICES.includes(cutoffDays as (typeof CUTOFF_CHOICES)[number]) ? null : (
                      <label className="on">{daysLabel(cutoffDays)} (from memory)</label>
                    )}
                  </fieldset>
                  <div className="select-row">
                    <button
                      type="button"
                      disabled={busy || stale.length === 0}
                      onClick={() =>
                        setStaleChecked(Object.fromEntries(stale.map((row) => [row.tab.tab_id, true])))
                      }
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      disabled={busy || staleSelected.length === 0}
                      onClick={() =>
                        setStaleChecked(Object.fromEntries(stale.map((row) => [row.tab.tab_id, false])))
                      }
                    >
                      Select none
                    </button>
                  </div>
                </div>
                <div className="sweep-groups">
                  {(staleGroups.length > 0 ? staleGroups : [{ title: "Unused tabs", tab_ids: stale.map((row) => row.tab.tab_id) }]).map(
                    (group) => {
                      const rows = group.tab_ids
                        .map((id) => stale.find((row) => row.tab.tab_id === id))
                        .filter((row): row is StaleTab => Boolean(row));
                      if (rows.length === 0) {
                        return null;
                      }
                      return (
                        <section className="sweep-group" key={group.title}>
                          <h3>
                            {group.title}
                            <span> · {rows.length}</span>
                          </h3>
                          <ul className="site-list pick">
                            {rows.map((row) => {
                              const learned = learnedClose.some((suffix) => hostMatches(row.host, suffix));
                              return (
                                <li key={row.tab.tab_id}>
                                  <label>
                                    <input
                                      type="checkbox"
                                      checked={Boolean(staleChecked[row.tab.tab_id])}
                                      onChange={(event) =>
                                        setStaleChecked((prev) => ({
                                          ...prev,
                                          [row.tab.tab_id]: event.target.checked,
                                        }))
                                      }
                                    />
                                    <span>
                                      <span className="title">{row.tab.title || row.host}</span>
                                      <span className="host">
                                        {row.host} · unused {daysLabel(row.daysIdle)}
                                        {learned ? " · learned: ok to close" : ""}
                                      </span>
                                    </span>
                                  </label>
                                </li>
                              );
                            })}
                          </ul>
                        </section>
                      );
                    },
                  )}
                </div>
                <button
                  type="button"
                  className="primary"
                  disabled={busy || staleSelected.length === 0}
                  onClick={() => void onCloseStale()}
                >
                  {allStaleSelected
                    ? `Close all ${plural(stale.length, "unused tab")}`
                    : `Close ${plural(staleSelected.length, "selected tab")}`}
                </button>
              </>
            ) : (
              <div className="toolbar">
                <fieldset className="cutoff">
                  <legend>Flag tabs unused for</legend>
                  {CUTOFF_CHOICES.map((days) => (
                    <label key={days} className={cutoffDays === days ? "on" : undefined}>
                      <input
                        type="radio"
                        name="cutoff-empty"
                        checked={cutoffDays === days}
                        onChange={() => void onCutoff(days)}
                      />
                      {daysLabel(days)}
                    </label>
                  ))}
                </fieldset>
              </div>
            )}
          </section>

          <p className="foot">
            {googleOk?.connected
              ? "Google Docs/Calendar connected."
              : googleOk?.configured
                ? "Docs are fake until you connect the throwaway Google account."
                : "Docs are fake until OAuth is configured."}{" "}
            <strong>Closes are real.</strong>{" "}
            {googleOk?.configured && !googleOk.connected ? (
              <button
                type="button"
                className="linkish"
                onClick={() => void googleAuthUrl().then((url) => chrome.tabs.create({ url }))}
              >
                Connect Google
              </button>
            ) : null}
          </p>
        </>
      )}
    </main>
  );
}
