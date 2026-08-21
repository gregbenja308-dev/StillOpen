import type { OpenTask } from "./schema";

export type FiledNote = {
  id: string;
  label: string;
  notes: string;
  urls: string[];
  closed_at: number;
};

const KEY = "filedNotes";
const MAX = 40;

export async function loadFiledNotes(): Promise<FiledNote[]> {
  const stored = await chrome.storage.local.get({ [KEY]: [] as FiledNote[] });
  const rows = stored[KEY];
  return Array.isArray(rows) ? (rows as FiledNote[]) : [];
}

export async function saveFiledNote(task: OpenTask): Promise<FiledNote | null> {
  const notes = (task.notes ?? "").trim();
  if (!notes) {
    return null;
  }
  const row: FiledNote = {
    id: crypto.randomUUID().replace(/-/g, "").slice(0, 26),
    label: task.label,
    notes,
    urls: task.urls.slice(0, 12),
    closed_at: Date.now(),
  };
  const existing = await loadFiledNotes();
  await chrome.storage.local.set({ [KEY]: [row, ...existing].slice(0, MAX) });
  return row;
}
