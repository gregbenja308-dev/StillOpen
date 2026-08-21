import { z } from "zod";

export const tabSnapshotSchema = z.object({
  tab_id: z.number().int(),
  window_id: z.number().int(),
  index: z.number().int(),
  url: z.string(),
  title: z.string(),
  pinned: z.boolean(),
  audible: z.boolean(),
  discarded: z.boolean(),
  active: z.boolean(),
  group_id: z.number().int(),
  group_title: z.string().optional().default(""),
  last_accessed_ms: z.number().nullable(),
  extract: z.string().nullable(),
});

export type TabSnapshot = z.infer<typeof tabSnapshotSchema>;

export const tabActionSchema = z.object({
  tab_id: z.number().int(),
  close_hint: z.enum(["never", "pre_check", "pre_uncheck"]),
  checked: z.boolean(),
  reason: z.string(),
  title: z.string().default(""),
});

export const planCardSchema = z.object({
  card_id: z.string(),
  verb: z.enum(["file", "watch", "finish", "decide", "kill"]),
  intention: z.string(),
  label: z.string(),
  tab_ids: z.array(z.number().int()),
  actions: z.array(tabActionSchema),
  notes: z.string().default(""),
});

export const planSchema = z.object({
  plan_id: z.string(),
  user_id: z.string(),
  command: z.string().nullable(),
  status: z.string(),
  cards: z.array(planCardSchema),
  blocked_tab_ids: z.array(z.number().int()),
});

export type Plan = z.infer<typeof planSchema>;
export type PlanCard = z.infer<typeof planCardSchema>;
export type TabAction = z.infer<typeof tabActionSchema>;

export const artifactSchema = z.object({
  record_id: z.string(),
  kind: z.enum(["doc", "event", "task", "mail"]),
  title: z.string().optional().default(""),
  google_id: z.string(),
  url: z.string(),
});

export const runResponseSchema = z.object({
  plan: planSchema,
  apply: z.object({
    close_tab_ids: z.array(z.number().int()),
    keep_tab_ids: z.array(z.number().int()),
  }),
  report: z.object({
    artifacts_ok: z.boolean(),
    apply_ok: z.boolean(),
    missing: z.array(z.string()),
    notes: z.string(),
  }),
  artifacts: z.array(artifactSchema),
  clerk: z.string().optional(),
});

export type RunResponse = z.infer<typeof runResponseSchema>;

export const undoRowSchema = z.object({
  tab_id: z.number().int(),
  url: z.string(),
  index: z.number().int(),
  pinned: z.boolean(),
  window_id: z.number().int(),
  title: z.string(),
});

export const closeBatchSchema = z.object({
  batch_id: z.string(),
  label: z.string(),
  closed_at: z.number(),
  rows: z.array(undoRowSchema),
  notes: z.string().default(""),
});

export type CloseBatch = z.infer<typeof closeBatchSchema>;

export const memoryProfileSchema = z
  .object({
    user_id: z.string(),
    stale_cutoff_days: z.number().int(),
    rules: z.array(z.any()),
    statements: z.array(z.any()),
    hosts: z.array(z.any()),
    mutations: z.array(z.any()),
    chats: z.array(z.any()),
  })
  .passthrough();

export const memoryDumpSchema = z.object({
  storage: z.object({
    engine: z.string(),
    backend: z.string(),
    path: z.string(),
    collections: z.array(z.string()),
    habit_fields: z.array(z.string()).optional(),
    note: z.string(),
  }),
  profile: memoryProfileSchema,
  scheduled: z.array(z.any()).optional(),
});

export const matchedTabSchema = z.object({
  tab_id: z.number().int(),
  title: z.string(),
  host: z.string(),
  url: z.string(),
});

export const chatResponseSchema = z.object({
  reply: z.string(),
  parser: z.string(),
  profile: memoryProfileSchema,
  storage: memoryDumpSchema.shape.storage,
  wants_close: z.boolean().default(false),
  label: z.string().default(""),
  matches: z.array(matchedTabSchema).default([]),
  unused_days: z.number().nullable().optional(),
  match_classes: z.array(z.string()).default([]),
});

export const scheduledCloseSchema = z.object({
  schedule_id: z.string(),
  user_id: z.string(),
  prompt: z.string(),
  label: z.string(),
  run_at: z.string(),
  hosts: z.array(z.string()),
  titles: z.array(z.string()),
  urls: z.array(z.string()),
  status: z.string(),
});

export type MemoryDump = z.infer<typeof memoryDumpSchema>;
export type MemoryProfile = z.infer<typeof memoryProfileSchema>;
export type ChatResponse = z.infer<typeof chatResponseSchema>;
export type MatchedTab = z.infer<typeof matchedTabSchema>;
export type ScheduledClose = z.infer<typeof scheduledCloseSchema>;

export const tabGroupSchema = z.object({
  title: z.string(),
  tab_ids: z.array(z.number().int()),
});

export const categorizeResponseSchema = z.object({
  groups: z.array(tabGroupSchema),
});

export type TabGroup = z.infer<typeof tabGroupSchema>;

export type ObserveKind =
  | "uncheck"
  | "undo"
  | "keep"
  | "user_close"
  | "stillopen_close"
  | "veto_intention";

export const openTaskSchema = z.object({
  task_id: z.string(),
  label: z.string(),
  tab_ids: z.array(z.number().int()),
  kind: z.enum(["durable", "ephemeral", "protected"]),
  hosts: z.array(z.string()).default([]),
  titles: z.array(z.string()).default([]),
  urls: z.array(z.string()).default([]),
  group_title: z.string().default(""),
  quiet: z.boolean().default(false),
  intention: z.string().default("unknown"),
  user_locked: z.boolean().default(false),
  notes: z.string().default(""),
});

export const inferTasksResponseSchema = z.object({
  tasks: z.array(openTaskSchema),
});

export type OpenTask = z.infer<typeof openTaskSchema>;
