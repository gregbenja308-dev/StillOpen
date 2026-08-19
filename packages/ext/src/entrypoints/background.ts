import { observeMemory } from "@/lib/api";
import { openDemoTabs } from "@/lib/demo";
import { armSchedule, runDueSchedule } from "@/lib/schedule";
import { getCutoffDays } from "@/lib/settings";
import { findStaleTabs, hostOf, setStaleBadge } from "@/lib/stale";
import {
  applyClose,
  consumeClosing,
  lookupTab,
  peekUndo,
  rememberTab,
  snapshotAllWindows,
  snapshotCurrentWindow,
  undoClose,
} from "@/lib/tabs";

const DAILY_ALARM = "stillopen-daily-scan";

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

  chrome.tabs.onUpdated.addListener((_id, _info, tab) => {
    void rememberTab(tab);
  });
  chrome.tabs.onCreated.addListener((tab) => {
    void rememberTab(tab);
  });
  chrome.tabs.onRemoved.addListener((tabId, info) => {
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
      message: { type?: string; tabIds?: number[]; scheduleId?: string; whenMs?: number },
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
      applyClose(message.tabIds ?? [])
        .then((result) => sendResponse({ ok: true, ...result }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message.type === "UNDO") {
      undoClose()
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
    if (message.type === "UNDO_PREVIEW") {
      peekUndo()
        .then((rows) => sendResponse({ ok: true, rows }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    return false;
  });
});
