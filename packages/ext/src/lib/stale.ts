import type { TabSnapshot } from "./schema";

const DAY_MS = 24 * 60 * 60 * 1000;

export type StaleTab = {
  tab: TabSnapshot;
  daysIdle: number;
  host: string;
};

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function hostMatches(host: string, suffix: string): boolean {
  const h = host.replace(/^www\./, "");
  const s = suffix.replace(/^www\./, "");
  return Boolean(s) && (h === s || h.endsWith(`.${s}`));
}

export function findStaleTabs(
  tabs: TabSnapshot[],
  cutoffDays: number,
  options?: { nowMs?: number; keepHosts?: string[] },
): StaleTab[] {
  const nowMs = options?.nowMs ?? Date.now();
  const keepHosts = options?.keepHosts ?? [];
  const cutoffMs = cutoffDays * DAY_MS;
  const stale: StaleTab[] = [];
  for (const tab of tabs) {
    if (tab.pinned || tab.audible) {
      continue;
    }
    if (tab.last_accessed_ms === null) {
      continue;
    }
    const host = hostOf(tab.url);
    if (keepHosts.some((suffix) => hostMatches(host, suffix))) {
      continue;
    }
    const idle = nowMs - tab.last_accessed_ms;
    if (idle < cutoffMs) {
      continue;
    }
    stale.push({
      tab,
      daysIdle: Math.max(1, Math.floor(idle / DAY_MS)),
      host,
    });
  }
  stale.sort((a, b) => b.daysIdle - a.daysIdle);
  return stale;
}

export async function setStaleBadge(count: number): Promise<void> {
  await chrome.action.setBadgeBackgroundColor({ color: "#1f4b3a" });
  await chrome.action.setBadgeText({ text: count > 0 ? String(Math.min(count, 99)) : "" });
}
