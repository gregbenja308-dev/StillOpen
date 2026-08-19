/** Synthetic house-hunt window. Public URLs only — never a personal dump. */
export const DEMO_COMMAND = "close the tabs relating to house shopping";

export const DEMO_TABS = [
  { url: "https://www.zillow.com/austin-tx/", label: "Zillow Austin" },
  { url: "https://www.redfin.com/city/30818/TX/Austin", label: "Redfin Austin" },
  { url: "https://www.zillow.com/homes/Austin-TX_rb/", label: "Zillow listings" },
  { url: "https://www.google.com/search?q=austin+homes+3+bedroom", label: "Google: austin homes" },
  { url: "https://www.nytimes.com/section/realestate", label: "NYT real estate" },
  { url: "https://www.chase.com/", label: "Chase (never sent to the model)" },
  { url: "https://www.realtor.com/realestateandhomes-search/Austin_TX", label: "Realtor Austin" },
] as const;

function hostPath(url: string): { host: string; path: string } | null {
  try {
    const parsed = new URL(url);
    return {
      host: parsed.hostname.replace(/^www\./, ""),
      path: parsed.pathname.replace(/\/$/, "") || "/",
    };
  } catch {
    return null;
  }
}

export function alreadyOpen(existingUrl: string, demoUrl: string): boolean {
  const live = hostPath(existingUrl);
  const demo = hostPath(demoUrl);
  if (!live || !demo) {
    return existingUrl.startsWith(demoUrl);
  }
  if (live.host !== demo.host) {
    return false;
  }
  return live.path === demo.path || live.path.startsWith(`${demo.path}/`);
}

function isHousingDemo(url: string): boolean {
  const parsed = hostPath(url);
  if (!parsed) {
    return false;
  }
  if (parsed.host === "google.com") {
    return parsed.path.startsWith("/search");
  }
  return ["zillow.com", "redfin.com", "realtor.com"].some(
    (host) => parsed.host === host || parsed.host.endsWith(`.${host}`),
  );
}

export async function openDemoTabs(): Promise<{ opened: number; already: number }> {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const live = tabs.map((tab) => tab.url ?? "");
  let opened = 0;
  let already = 0;
  for (const demo of DEMO_TABS) {
    if (live.some((url) => alreadyOpen(url, demo.url))) {
      already += 1;
      continue;
    }
    await chrome.tabs.create({ url: demo.url, active: false });
    opened += 1;
  }
  const after = await chrome.tabs.query({ currentWindow: true });
  const housing = after.filter(
    (tab): tab is chrome.tabs.Tab & { id: number } =>
      typeof tab.id === "number" && Boolean(tab.url) && isHousingDemo(tab.url ?? ""),
  );
  if (housing.length >= 2) {
    try {
      const groupId = await chrome.tabs.group({ tabIds: housing.map((tab) => tab.id) });
      await chrome.tabGroups.update(groupId, { title: "Austin rentals", collapsed: false });
    } catch {
      // Grouping is a demo hint; ignore if Chrome refuses.
    }
  }
  return { opened, already };
}
