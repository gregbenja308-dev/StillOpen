import {
  chatResponseSchema,
  inferTasksResponseSchema,
  memoryDumpSchema,
  planSchema,
  runResponseSchema,
  scheduledCloseSchema,
  type ChatResponse,
  type MemoryDump,
  type MatchedTab,
  type ObserveKind,
  type OpenTask,
  type Plan,
  type RunResponse,
  type ScheduledClose,
  type TabSnapshot,
} from "./schema";

const DEFAULT_API = "http://127.0.0.1:8080";

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

async function readJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    throw new Error(`API ${response.status}`);
  }
  return response.json();
}

export async function createPlan(
  command: string | null,
  tabs: TabSnapshot[],
  opts: { forceFile?: boolean } = {},
): Promise<Plan> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/plans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: uid,
        command,
        tabs,
        force_file: Boolean(opts.forceFile),
      }),
    }),
  );
  return planSchema.parse(body);
}

export async function googleAuthUrl(): Promise<string> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  return `${base}/v1/auth/google?user_id=${encodeURIComponent(uid)}`;
}

export async function googleAuthStatus(): Promise<{ connected: boolean; configured: boolean }> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = (await readJson(
    await fetch(`${base}/v1/auth/google/status?user_id=${encodeURIComponent(uid)}`),
  )) as { connected?: string; configured?: string };
  return { connected: body.connected === "yes", configured: body.configured === "yes" };
}

export async function runPlan(
  planId: string,
  overrides: Array<{ tab_id: number; checked: boolean }>,
): Promise<RunResponse> {
  const base = await apiBase();
  const body = await readJson(
    await fetch(`${base}/v1/plans/${planId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overrides }),
    }),
  );
  return runResponseSchema.parse(body);
}

export async function getMemory(): Promise<MemoryDump> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(await fetch(`${base}/v1/memory?user_id=${encodeURIComponent(uid)}`));
  return memoryDumpSchema.parse(body);
}

export async function chatMemory(message: string, tabs: TabSnapshot[] = []): Promise<ChatResponse> {
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/memory/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid, message, tabs }),
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

export async function inferTasks(tabs: TabSnapshot[], cutoffDays = 7): Promise<OpenTask[]> {
  if (tabs.length === 0) {
    return [];
  }
  const [base, uid] = await Promise.all([apiBase(), userId()]);
  const body = await readJson(
    await fetch(`${base}/v1/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: uid, tabs, cutoff_days: cutoffDays }),
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
