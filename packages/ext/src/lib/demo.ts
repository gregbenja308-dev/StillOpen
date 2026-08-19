/** Synthetic messy window. Public URLs only — never a personal dump. */
export const DEMO_COMMAND = "close the tabs relating to house shopping";

export const DEMO_TABS = [
  { url: "https://www.zillow.com/austin-tx/", label: "Zillow Austin" },
  { url: "https://www.redfin.com/city/30818/TX/Austin", label: "Redfin Austin" },
  { url: "https://www.zillow.com/homes/Austin-TX_rb/", label: "Zillow listings" },
  { url: "https://www.google.com/search?q=austin+homes+3+bedroom", label: "Google: austin homes" },
  { url: "https://www.nytimes.com/section/realestate", label: "NYT real estate" },
  { url: "https://www.chase.com/", label: "Chase (never sent to the model)" },
  { url: "https://www.realtor.com/realestateandhomes-search/Austin_TX", label: "Realtor Austin" },
  { url: "https://www.apartments.com/austin-tx/", label: "Apartments.com Austin" },
  { url: "https://austin.craigslist.org/search/apa", label: "Craigslist Austin apts" },
  { url: "https://www.merriam-webster.com/dictionary/ephemeral", label: "Dictionary: ephemeral" },
  { url: "https://en.wikipedia.org/wiki/Ephemeral", label: "Wikipedia: Ephemeral" },
  { url: "https://www.google.com/search?q=what+does+ephemeral+mean", label: "Google: ephemeral" },
  { url: "https://www.amazon.com/s?k=macbook+air", label: "Amazon: MacBook Air" },
  { url: "https://www.bestbuy.com/site/searchpage.jsp?st=macbook+air", label: "Best Buy: MacBook Air" },
  { url: "https://www.apple.com/macbook-air/", label: "Apple MacBook Air" },
  { url: "https://www.ups.com/track?loc=en_US", label: "UPS tracking" },
  { url: "https://www.bbc.com/news", label: "BBC News" },
  { url: "https://github.com/google/adk-python", label: "GitHub: google/adk-python" },
  { url: "https://www.reddit.com/r/AustinApartments/", label: "Reddit: AustinApartments" },
  { url: "https://stackoverflow.com/questions/tagged/python", label: "Stack Overflow: python" },
  { url: "https://www.nytimes.com/section/technology", label: "NYT technology" },
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
  return { opened, already };
}
