import { finishSchedule, observeMemory } from "@/lib/api";
import { applyClose, lookupTab, rememberTab } from "@/lib/tabs";
import { hostOf } from "@/lib/stale";

const PREFIX = "stillopen-sched-";
const STORE = "scheduledCloses";

export type StoredSchedule = {
  scheduleId: string;
  urls: string[];
  titles: string[];
};

export async function armSchedule(scheduleId: string, whenMs: number, tabIds: number[]): Promise<void> {
  const urls: string[] = [];
  const titles: string[] = [];
  for (const id of tabIds) {
    const row = await lookupTab(id);
    if (!row) {
      continue;
    }
    urls.push(row.url);
    titles.push(row.title);
  }
  const stored = await chrome.storage.local.get({ [STORE]: [] as StoredSchedule[] });
  const rows = (stored[STORE] ?? []) as StoredSchedule[];
  const next = rows.filter((row) => row.scheduleId !== scheduleId);
  next.push({ scheduleId, urls, titles });
  await chrome.storage.local.set({ [STORE]: next });
  await chrome.alarms.create(`${PREFIX}${scheduleId}`, { when: whenMs });
}

export async function runDueSchedule(alarmName: string): Promise<void> {
  if (!alarmName.startsWith(PREFIX)) {
    return;
  }
  const scheduleId = alarmName.slice(PREFIX.length);
  const stored = await chrome.storage.local.get({ [STORE]: [] as StoredSchedule[] });
  const rows = (stored[STORE] ?? []) as StoredSchedule[];
  const job = rows.find((row) => row.scheduleId === scheduleId);
  if (!job) {
    return;
  }
  const live = await chrome.tabs.query({});
  for (const tab of live) {
    await rememberTab(tab);
  }
  const ids: number[] = [];
  for (const tab of live) {
    if (typeof tab.id !== "number" || !tab.url) {
      continue;
    }
    if (job.urls.some((saved) => samePage(tab.url ?? "", saved))) {
      ids.push(tab.id);
    }
  }
  if (ids.length > 0) {
    await applyClose(ids);
    for (const url of job.urls) {
      await observeMemory({
        kind: "stillopen_close",
        host: hostOf(url),
        title: job.titles[job.urls.indexOf(url)] ?? "",
        source: "schedule",
      });
    }
  }
  await chrome.storage.local.set({
    [STORE]: rows.filter((row) => row.scheduleId !== scheduleId),
  });
  await finishSchedule(scheduleId, ids.length > 0 ? "done" : "missed");
}

function samePage(live: string, saved: string): boolean {
  try {
    const a = new URL(live);
    const b = new URL(saved);
    const hostA = a.hostname.replace(/^www\./, "");
    const hostB = b.hostname.replace(/^www\./, "");
    const pathA = a.pathname.replace(/\/$/, "") || "/";
    const pathB = b.pathname.replace(/\/$/, "") || "/";
    return hostA === hostB && pathA === pathB;
  } catch {
    return live === saved;
  }
}
