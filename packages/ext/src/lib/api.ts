import {
  chatResponseSchema,
  finishTaskResponseSchema,
  inferTasksResponseSchema,
  memoryDumpSchema,
  registryResponseSchema,
  scheduledCloseSchema,
  stillGoingResponseSchema,
  type ChatResponse,
  type FinishTaskResponse,
  type MemoryDump,
  type MatchedTab,
  type ObserveKind,
  type OpenTask,
  type RegistryResponse,
  type ScheduledClose,
  type StillGoingResponse,
  type TabSnapshot,
} from "./schema";

const DEFAULT_API = "https://stillopen-tqodm6o6za-uc.a.run.app";

export async function apiBase(): Promise<string> {
  const stored = await chrome.storage.local.get({ apiBase: DEFAULT_API });
  return typeof stored.apiBase === "string" ? stored.apiBase : DEFAULT_API;
}

export async function userId(): Promise<string> {
  const stored = await chrome.storage.local.get({ userId: "" });
  if (typeof stored.userId === "string" && stored.userId.length > 0) {
    return stored.userId;
  }
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ userId: id });
  return id;
}

async function userToken(): Promise<string> {
  const stored = await chrome.storage.local.get({ userToken: "" });
  if (typeof stored.userToken === "string" && stored.userToken.length > 0) {
    return stored.userToken;
  }
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  try {
    const resp = await fetch(`${base}/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid }),
    });
    if (!resp.ok) return "";
    const body = (await resp.json()) as { token?: string };
    const token = typeof body.token === "string" ? body.token : "";
    if (token) {
      await chrome.storage.local.set({ userToken: token });
    }
    return token;
  } catch {
    return "";
  }
}

async function writeHeaders(): Promise<Record<string, string>> {
  const token = await userToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Stillopen-User-Token"] = token;
  }
  return headers;
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    let extra = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (Array.isArray(body.detail) && body.detail[0]) {
        const first = body.detail[0] as { loc?: unknown[]; msg?: string };
        extra = `: ${first.msg ?? JSON.stringify(first)}`;
      } else if (typeof body.detail === "string") {
        extra = `: ${body.detail}`;
      }
    } catch {
      /* ignore */
    }
    throw new Error(`API ${response.status}${extra}`);
  }
  return response.json();
}

export async function getMemory(): Promise<MemoryDump> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(await fetch(`${base}/v1/memory?user_id=${encodeURIComponent(uid)}`));
  return memoryDumpSchema.parse(body);
}

export async function chatMemory(
  message: string,
  tabs: TabSnapshot[] = [],
  tasks: OpenTask[] = [],
): Promise<ChatResponse> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/memory/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid, message, tabs, tasks }),
    }),
  );
  return chatResponseSchema.parse(body);
}

export async function observeMemory(input: {
  kind: ObserveKind;
  host?: string;
  title?: string;
  source?: string;
  stale_cutoff_days?: number;
}): Promise<MemoryDump | null> {
  try {
    const [base, uid] = await Promise.all([apiBase(), userId()]);
    const body = await readJson(
      await fetch(`${base}/v1/memory/observe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: uid,
          kind: input.kind,
          host: input.host ?? "",
          title: input.title ?? "",
          source: input.source ?? "chrome",
          stale_cutoff_days: input.stale_cutoff_days ?? null,
        }),
      }),
    );
    return memoryDumpSchema.parse(body);
  } catch {
    return null;
  }
}

export async function scheduleClose(input: {
  prompt: string;
  label: string;
  run_at: string;
  matches: MatchedTab[];
  schedule_id: string;
}): Promise<ScheduledClose> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/memory/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid, ...input }),
    }),
  );
  return scheduledCloseSchema.parse(body);
}

export async function inferTasks(
  tabs: TabSnapshot[],
  opts: {
    cutoffDays?: number;
    existing?: OpenTask[];
    ignoredUrls?: string[];
    fast?: boolean;
  } = {},
): Promise<OpenTask[]> {
  if (tabs.length === 0) {
    return [];
  }
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: uid,
        tabs,
        cutoff_days: opts.cutoffDays ?? 7,
        existing: opts.existing ?? [],
        ignored_urls: opts.ignoredUrls ?? [],
        fast: Boolean(opts.fast),
      }),
    }),
  );
  return inferTasksResponseSchema.parse(body).tasks;
}

export async function finishSchedule(scheduleId: string, status = "done"): Promise<void> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  await fetch(`${base}/v1/memory/schedule/${encodeURIComponent(scheduleId)}/done`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: uid, status }),
  });
}

export async function finishTask(input: {
  task: OpenTask;
  tabs: TabSnapshot[];
  fileToGoogle?: boolean | null;
}): Promise<FinishTaskResponse> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const headers = await writeHeaders();
  const body = await readJson(
    await fetch(`${base}/v1/tasks/finish`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        user_id: uid,
        task_id: input.task.task_id,
        label: input.task.label || "Closed",
        notes: input.task.notes ?? "",
        tabs: input.tabs.filter((tab) => input.task.tab_ids.includes(tab.tab_id)),
        intention: input.task.intention || "unknown",
        kind: input.task.kind,
        file_to_google: input.fileToGoogle ?? null,
      }),
    }),
  );
  const parsed = finishTaskResponseSchema.parse(body);
  const audit = parsed.audit_url.startsWith("http")
    ? parsed.audit_url
    : `${base}${parsed.audit_url}`;
  return { ...parsed, audit_url: audit };
}

export async function stillGoing(input: {
  task: OpenTask;
  urls: string[];
}): Promise<StillGoingResponse> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const headers = await writeHeaders();
  const body = await readJson(
    await fetch(`${base}/v1/tasks/still-going`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        user_id: uid,
        task_id: input.task.task_id,
        label: input.task.label || "Track",
        urls: input.urls,
      }),
    }),
  );
  return stillGoingResponseSchema.parse(body);
}

export async function agentsRegistry(): Promise<RegistryResponse> {
  const base = await apiBase();
  const body = await readJson(await fetch(`${base}/v1/agents/registry`));
  return registryResponseSchema.parse(body);
}
