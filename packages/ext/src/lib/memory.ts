import type { MemoryDump, MemoryProfile } from "./schema";

export function keepHosts(profile: MemoryProfile | undefined): string[] {
  if (!profile) {
    return [];
  }
  return (profile.rules as Array<{ host_suffix?: string; close_policy?: string }>)
    .filter((rule) => rule.close_policy === "always_keep" || rule.close_policy === "never_close")
    .map((rule) => String(rule.host_suffix ?? ""))
    .filter(Boolean);
}

export function closeOkHosts(profile: MemoryProfile | undefined): string[] {
  if (!profile) {
    return [];
  }
  return (profile.rules as Array<{ host_suffix?: string; close_policy?: string }>)
    .filter((rule) => rule.close_policy === "file_then_close")
    .map((rule) => String(rule.host_suffix ?? ""))
    .filter(Boolean);
}

export function dumpFromChat(profile: MemoryProfile, storage: MemoryDump["storage"]): MemoryDump {
  return { profile, storage };
}
