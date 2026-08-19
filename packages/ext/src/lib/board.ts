import type { OpenTask, TabSnapshot } from "./schema";
import { hostOf } from "./stale";

export type Board = {
  tasks: OpenTask[];
  ignored: string[];
};

const KEY = "taskBoard";

export function canonUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "").toLowerCase();
    const path = parsed.pathname.replace(/\/$/, "") || "/";
    return `${host}${path}`;
  } catch {
    return url;
  }
}

export async function loadBoard(): Promise<Board> {
  const stored = await chrome.storage.local.get({ [KEY]: { tasks: [], ignored: [] } });
  const raw = stored[KEY] as Board;
  return {
    tasks: Array.isArray(raw?.tasks) ? raw.tasks : [],
    ignored: Array.isArray(raw?.ignored) ? raw.ignored : [],
  };
}

export async function saveBoard(board: Board): Promise<void> {
  await chrome.storage.local.set({ [KEY]: board });
}

export function pruneBoard(board: Board, live: TabSnapshot[]): Board {
  const byId = new Map(live.map((tab) => [tab.tab_id, tab]));
  const byCanon = new Map<string, TabSnapshot>();
  for (const tab of live) {
    byCanon.set(canonUrl(tab.url), tab);
  }
  const tasks = board.tasks
    .map((task) => {
      const members: TabSnapshot[] = [];
      const seen = new Set<number>();
      for (const id of task.tab_ids) {
        const tab = byId.get(id);
        if (tab && !seen.has(tab.tab_id)) {
          members.push(tab);
          seen.add(tab.tab_id);
        }
      }
      for (const url of task.urls ?? []) {
        const tab = byCanon.get(canonUrl(url));
        if (tab && !seen.has(tab.tab_id)) {
          members.push(tab);
          seen.add(tab.tab_id);
        }
      }
      if (members.length === 0 && !task.user_locked) {
        return null;
      }
      return withMembers(task, members);
    })
    .filter((task): task is OpenTask => task !== null);

  const assigned = new Set(tasks.flatMap((task) => task.tab_ids));
  const ignored = new Set(board.ignored);
  const extras = live.filter(
    (tab) => !assigned.has(tab.tab_id) && !ignored.has(canonUrl(tab.url)),
  );
  let next = tasks;
  for (const tab of extras) {
    const attached = attachLocal(next, tab);
    if (attached) {
      next = attached;
    }
  }
  return { tasks: next, ignored: board.ignored };
}

export function looseTabs(live: TabSnapshot[], board: Board): TabSnapshot[] {
  const assigned = new Set(board.tasks.flatMap((task) => task.tab_ids));
  return live.filter((tab) => !assigned.has(tab.tab_id));
}

export function attachLocal(tasks: OpenTask[], tab: TabSnapshot): OpenTask[] | null {
  const host = hostOf(tab.url);
  let best = -1;
  let bestI = -1;
  tasks.forEach((task, index) => {
    if (task.kind === "protected") {
      return;
    }
    let score = task.hosts.includes(host) ? 3 : 0;
    const blob = `${task.label} ${task.titles.join(" ")}`.toLowerCase();
    const words = tab.title.toLowerCase().split(/\W+/).filter((w) => w.length > 3);
    for (const word of words) {
      if (blob.includes(word)) {
        score += 1;
      }
    }
    if (score > best) {
      best = score;
      bestI = index;
    }
  });
  if (best < 2 || bestI < 0) {
    return null;
  }
  const task = tasks[bestI];
  if (task.tab_ids.includes(tab.tab_id)) {
    return tasks;
  }
  const copy = [...tasks];
  copy[bestI] = {
    ...task,
    tab_ids: [...task.tab_ids, tab.tab_id],
    urls: [...(task.urls ?? []), tab.url],
    titles: [...task.titles, tab.title].slice(0, 8),
    hosts: sortedHosts([...task.hosts, host]),
  };
  return copy;
}

function sortedHosts(hosts: string[]): string[] {
  return [...new Set(hosts.filter(Boolean))].sort();
}

export function withMembers(task: OpenTask, members: TabSnapshot[]): OpenTask {
  return {
    ...task,
    tab_ids: members.map((tab) => tab.tab_id),
    urls: members.map((tab) => tab.url),
    titles: members.map((tab) => tab.title).slice(0, 8),
    hosts: sortedHosts(members.map((tab) => hostOf(tab.url))),
  };
}

export function newTask(label = "New task"): OpenTask {
  return {
    task_id: crypto.randomUUID().replace(/-/g, "").slice(0, 26),
    label,
    tab_ids: [],
    kind: "ephemeral",
    hosts: [],
    titles: [],
    urls: [],
    group_title: "",
    quiet: false,
    intention: "unknown",
    user_locked: true,
  };
}

export function moveTab(
  board: Board,
  tabId: number,
  fromId: string,
  toId: string,
  live: TabSnapshot[],
): Board {
  if (fromId === toId) {
    return board;
  }
  const tab = live.find((row) => row.tab_id === tabId);
  const from = board.tasks.find((task) => task.task_id === fromId);
  const to = board.tasks.find((task) => task.task_id === toId);
  if (!from || !to || to.kind === "protected" || from.kind === "protected") {
    return board;
  }
  const ignored = board.ignored.filter((url) => {
    const memberUrl = tab?.url ?? from.urls[from.tab_ids.indexOf(tabId)] ?? "";
    return canonUrl(url) !== canonUrl(memberUrl);
  });
  const tasks = board.tasks
    .map((task) => {
      if (task.task_id === fromId) {
        const members = live.filter((row) => task.tab_ids.includes(row.tab_id) && row.tab_id !== tabId);
        if (members.length === 0 && !task.user_locked) {
          return null;
        }
        return { ...withMembers(task, members), user_locked: true };
      }
      if (task.task_id === toId) {
        const members = [
          ...live.filter((row) => task.tab_ids.includes(row.tab_id)),
          ...(tab && !task.tab_ids.includes(tabId) ? [tab] : []),
        ];
        return { ...withMembers(task, members), user_locked: true };
      }
      return task;
    })
    .filter((task): task is OpenTask => task !== null);
  return { tasks, ignored };
}

export function dropLoose(board: Board, tabId: number, toId: string, live: TabSnapshot[]): Board {
  const tab = live.find((row) => row.tab_id === tabId);
  const to = board.tasks.find((task) => task.task_id === toId);
  if (!tab || !to || to.kind === "protected") {
    return board;
  }
  const ignored = board.ignored.filter((url) => canonUrl(url) !== canonUrl(tab.url));
  const tasks = board.tasks.map((task) => {
    if (task.task_id !== toId) {
      return task;
    }
    if (task.tab_ids.includes(tabId)) {
      return { ...task, user_locked: true };
    }
    const members = [...live.filter((row) => task.tab_ids.includes(row.tab_id)), tab];
    return { ...withMembers(task, members), user_locked: true };
  });
  return { tasks, ignored };
}

export function ignoreTab(board: Board, taskId: string, tabId: number, live: TabSnapshot[]): Board {
  const tab = live.find((row) => row.tab_id === tabId);
  const task = board.tasks.find((row) => row.task_id === taskId);
  if (!task || task.kind === "protected") {
    return board;
  }
  const url = tab?.url ?? task.urls[task.tab_ids.indexOf(tabId)] ?? "";
  const ignored = url ? [...new Set([...board.ignored, canonUrl(url)])] : board.ignored;
  const tasks = board.tasks
    .map((row) => {
      if (row.task_id !== taskId) {
        return row;
      }
      const members = live.filter((item) => row.tab_ids.includes(item.tab_id) && item.tab_id !== tabId);
      if (members.length === 0 && !row.user_locked) {
        return null;
      }
      return { ...withMembers(row, members), user_locked: true };
    })
    .filter((row): row is OpenTask => row !== null);
  return { tasks, ignored };
}
