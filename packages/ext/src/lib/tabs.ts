import { isCloseableUrl, redactUrl } from "./redact";
import type { TabSnapshot, UndoRow } from "./schema";

const closingByUs = new Set<number>();

function isHttpTab(tab: chrome.tabs.Tab): tab is chrome.tabs.Tab & { id: number; url: string } {
  return typeof tab.id === "number" && isCloseableUrl(tab.url ?? "");
}

async function persistUndo(rows: UndoRow[], mode: "replace" | "merge"): Promise<void> {
  if (mode === "replace") {
    await chrome.storage.session.set({ undoMap: rows });
    return;
  }
  const stored = await chrome.storage.session.get({ undoMap: [] as UndoRow[] });
  const byId = new Map(((stored.undoMap ?? []) as UndoRow[]).map((row) => [row.tab_id, row]));
  for (const row of rows) {
    byId.set(row.tab_id, row);
  }
  await chrome.storage.session.set({ undoMap: [...byId.values()] });
}

async function snapshot(query: chrome.tabs.QueryInfo, mode: "replace" | "merge"): Promise<TabSnapshot[]> {
  const tabs = await chrome.tabs.query(query);
  const live = tabs.filter(isHttpTab);
  const undo: UndoRow[] = live.map((tab) => ({
    tab_id: tab.id,
    url: tab.url,
    index: tab.index,
    pinned: Boolean(tab.pinned),
    window_id: tab.windowId,
    title: tab.title ?? "",
  }));
  await persistUndo(undo, mode);

  const groupIds = [...new Set(live.map((tab) => tab.groupId).filter((id) => id >= 0))];
  const groupTitles = new Map<number, string>();
  await Promise.all(
    groupIds.map(async (id) => {
      try {
        const group = await chrome.tabGroups.get(id);
        groupTitles.set(id, group.title ?? "");
      } catch {
        groupTitles.set(id, "");
      }
    }),
  );

  return live.map((tab) => ({
    tab_id: tab.id,
    window_id: tab.windowId,
    index: tab.index,
    url: redactUrl(tab.url),
    title: tab.title ?? "",
    pinned: Boolean(tab.pinned),
    audible: Boolean(tab.audible),
    discarded: Boolean(tab.discarded),
    active: Boolean(tab.active),
    group_id: tab.groupId ?? -1,
    group_title: groupTitles.get(tab.groupId ?? -1) ?? "",
    last_accessed_ms: tab.lastAccessed && tab.lastAccessed > 0 ? tab.lastAccessed : null,
    extract: null,
  }));
}

export function snapshotCurrentWindow(): Promise<TabSnapshot[]> {
  return snapshot({ currentWindow: true }, "merge");
}

export function snapshotAllWindows(): Promise<TabSnapshot[]> {
  return snapshot({}, "replace");
}

export async function applyClose(tabIds: number[]): Promise<{ closed: number; rows: UndoRow[] }> {
  const stored = await chrome.storage.session.get({ undoMap: [] as UndoRow[] });
  const undoMap = (stored.undoMap ?? []) as UndoRow[];
  const byId = new Map(undoMap.map((row) => [row.tab_id, row]));
  const toClose: number[] = [];
  for (const id of tabIds) {
    const row = byId.get(id);
    if (!row || row.pinned || !isCloseableUrl(row.url)) {
      continue;
    }
    toClose.push(id);
  }
  const rows = undoMap.filter((row) => toClose.includes(row.tab_id));
  if (toClose.length === 0) {
    return { closed: 0, rows: [] };
  }
  for (const id of toClose) {
    closingByUs.add(id);
  }
  await chrome.tabs.remove(toClose);
  await chrome.storage.session.set({ lastClosed: rows });
  return { closed: toClose.length, rows };
}

export async function peekUndo(): Promise<UndoRow[]> {
  const stored = await chrome.storage.session.get({ lastClosed: [] as UndoRow[] });
  return [...((stored.lastClosed ?? []) as UndoRow[])].sort((a, b) => a.index - b.index);
}

export async function undoClose(): Promise<number> {
  const stored = await chrome.storage.session.get({ lastClosed: [] as UndoRow[] });
  const lastClosed = [...((stored.lastClosed ?? []) as UndoRow[])].sort(
    (a, b) => a.index - b.index,
  );
  for (const row of lastClosed) {
    try {
      await chrome.tabs.create({
        url: row.url,
        index: row.index,
        pinned: row.pinned,
        windowId: row.window_id,
        active: false,
      });
    } catch {
      await chrome.tabs.create({ url: row.url, active: false });
    }
  }
  await chrome.storage.session.set({ lastClosed: [] });
  return lastClosed.length;
}

export async function rememberTab(tab: chrome.tabs.Tab): Promise<void> {
  if (!isHttpTab(tab)) {
    return;
  }
  await persistUndo(
    [
      {
        tab_id: tab.id,
        url: tab.url,
        index: tab.index,
        pinned: Boolean(tab.pinned),
        window_id: tab.windowId,
        title: tab.title ?? "",
      },
    ],
    "merge",
  );
}

export async function lookupTab(tabId: number): Promise<UndoRow | null> {
  const stored = await chrome.storage.session.get({ undoMap: [] as UndoRow[] });
  return ((stored.undoMap ?? []) as UndoRow[]).find((row) => row.tab_id === tabId) ?? null;
}

export function consumeClosing(tabId: number): boolean {
  const ours = closingByUs.has(tabId);
  closingByUs.delete(tabId);
  return ours;
}
