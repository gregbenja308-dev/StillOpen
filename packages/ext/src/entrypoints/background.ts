import { observeMemory } from "@/lib/api";
import { openDemoTabs } from "@/lib/demo";
import { armSchedule, runDueSchedule } from "@/lib/schedule";
import { getCutoffDays } from "@/lib/settings";
import { findStaleTabs, hostOf, setStaleBadge } from "@/lib/stale";
import {
  applyClose,
  consumeClosing,
  lookupTab,
  peekBatches,
  rememberTab,
  restoreBatch,
  snapshotAllWindows,
  snapshotCurrentWindow,
  updateBatchNotes,
} from "@/lib/tabs";

const DAILY_ALARM = "stillopen-daily-scan";

function ping(reason: "created" | "removed" | "updated", tabId?: number): void {
  chrome.runtime.sendMessage({ type: "TABS_CHANGED", reason, tabId }).catch(() => undefined);
}

async function refreshBadge(): Promise<number> {
  const [tabs, cutoff] = await Promise.all([snapshotAllWindows(), getCutoffDays()]);
  const stale = findStaleTabs(tabs, cutoff);
  await setStaleBadge(stale.length);
  return stale.length;
}

export default defineBackground(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  void chrome.alarms.create(DAILY_ALARM, { periodInMinutes: 60 * 24, delayInMinutes: 1 });
  void refreshBadge();

  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === DAILY_ALARM) {
      void refreshBadge();
      return;
    }
    void runDueSchedule(alarm.name);
  });

  chrome.tabs.onUpdated.addListener((id, info, tab) => {
    void rememberTab(tab);
    if (info.url || info.title) {
      ping("updated", id);
    }
  });
  chrome.tabs.onCreated.addListener((tab) => {
    void rememberTab(tab);
    ping("created", tab.id);
  });
  chrome.tabs.onRemoved.addListener((tabId, info) => {
    ping("removed", tabId);
    if (info.isWindowClosing) {
      return;
    }
    void (async () => {
      const row = await lookupTab(tabId);
      if (!row) {
        return;
      }
      const ours = consumeClosing(tabId);
      await observeMemory({
        kind: ours ? "stillopen_close" : "user_close",
        host: hostOf(row.url),
        title: row.title,
        source: ours ? "stillopen" : "chrome",
      });
    })();
  });

  chrome.action.onClicked.addListener((tab) => {
    if (tab.windowId !== undefined) {
      void chrome.sidePanel.open({ windowId: tab.windowId });
    }
  });

  chrome.runtime.onMessage.addListener(
    (
      message: {
        type?: string;
        tabIds?: number[];
        scheduleId?: string;
        whenMs?: number;
        label?: string;
        batchId?: string;
        notes?: string;
        filingUrl?: string | null;
        auditUrl?: string | null;
        clerk?: string | null;
      },
      _sender,
      sendResponse,
    ) => {
    if (message.type === "SNAPSHOT") {
      snapshotCurrentWindow()
        .then((tabs) => sendResponse({ ok: true, tabs }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "SCAN") {
      snapshotAllWindows()
        .then(async (tabs) => {
          const cutoff = await getCutoffDays();
          const stale = findStaleTabs(tabs, cutoff);
          await setStaleBadge(stale.length);
          sendResponse({ ok: true, tabs, cutoffDays: cutoff });
        })
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "APPLY_CLOSE") {
      applyClose(
        message.tabIds ?? [],
        typeof message.label === "string" ? message.label : "Closed",
        typeof message.notes === "string" ? message.notes : "",
        {
          filingUrl: typeof message.filingUrl === "string" ? message.filingUrl : null,
          auditUrl: typeof message.auditUrl === "string" ? message.auditUrl : null,
          clerk: typeof message.clerk === "string" ? message.clerk : null,
        },
      )
        .then((result) => sendResponse({ ok: true, ...result }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "RESTORE_BATCH") {
      restoreBatch(typeof message.batchId === "string" ? message.batchId : "")
        .then((restored) => sendResponse({ ok: true, restored }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "UPDATE_BATCH_NOTES") {
      updateBatchNotes(
        typeof message.batchId === "string" ? message.batchId : "",
        typeof message.notes === "string" ? message.notes : "",
      )
        .then((batch) => sendResponse({ ok: true, batch }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "UNDO") {
      restoreBatch(typeof message.batchId === "string" ? message.batchId : "")
        .then((restored) => sendResponse({ ok: true, restored }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "OPEN_DEMO") {
      openDemoTabs()
        .then((result) => sendResponse({ ok: true, ...result }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "SCHEDULE_CLOSE") {
      const scheduleId = message.scheduleId ?? "";
      const whenMs = message.whenMs ?? 0;
      armSchedule(scheduleId, whenMs, message.tabIds ?? [])
        .then(() => sendResponse({ ok: true }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "UNDO_PREVIEW" || message.type === "RESTORE_PREVIEW") {
      peekBatches()
        .then((batches) => sendResponse({ ok: true, batches }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    return false;
  });
});
