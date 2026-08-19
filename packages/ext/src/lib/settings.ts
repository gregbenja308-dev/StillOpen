const DEFAULT_CUTOFF_DAYS = 7;
const KEY = "staleCutoffDays";

export async function getCutoffDays(): Promise<number> {
  const stored = await chrome.storage.local.get({ [KEY]: DEFAULT_CUTOFF_DAYS });
  const value = Number(stored[KEY]);
  return Number.isFinite(value) && value >= 1 ? value : DEFAULT_CUTOFF_DAYS;
}

export async function setCutoffDays(days: number): Promise<void> {
  await chrome.storage.local.set({ [KEY]: days });
}

export const CUTOFF_CHOICES = [3, 7, 14, 30] as const;
