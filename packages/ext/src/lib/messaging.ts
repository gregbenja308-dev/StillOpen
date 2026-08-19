import type { CloseBatch, TabSnapshot, UndoRow } from "./schema";

export type SnapshotReply = { ok: true; tabs: TabSnapshot[] } | { ok: false; error: string };
export type ScanReply =
  | { ok: true; tabs: TabSnapshot[]; cutoffDays: number }
  | { ok: false; error: string };
export type CloseReply =
  | { ok: true; closed: number; rows: UndoRow[]; batch: CloseBatch | null }
  | { ok: false; error: string };
export type UndoReply = { ok: true; restored: number } | { ok: false; error: string };
export type RestorePreviewReply = { ok: true; batches: CloseBatch[] } | { ok: false; error: string };
export type DemoReply =
  | { ok: true; opened: number; already: number }
  | { ok: false; error: string };
export type ScheduleReply = { ok: true } | { ok: false; error: string };
export type TabChangeMsg = { type: "TABS_CHANGED"; reason: "created" | "removed" | "updated"; tabId?: number };

export async function send<T>(payload: Record<string, unknown>): Promise<T> {
  return chrome.runtime.sendMessage(payload) as Promise<T>;
}
