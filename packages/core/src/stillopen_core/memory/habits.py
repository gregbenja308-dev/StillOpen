"""Apply / mutate habits from chat, closes, and explicit keep/undo."""

from __future__ import annotations

from stillopen_core.schemas.habit import (
    MAX_MUTATIONS,
    ClosePolicy,
    FeedbackKind,
    HabitEvent,
    HabitProfile,
    HabitRule,
    Mutation,
    policy_to_hint,
)
from stillopen_core.schemas.tab import CloseHint, SanitizedTab

_KEEP_KINDS = {
    FeedbackKind.UNCHECK,
    FeedbackKind.UNDO,
    FeedbackKind.VETO_INTENTION,
    FeedbackKind.KEEP,
}
_USER_CLOSE_INFER_AT = 2


def mutate(profile: HabitProfile, event: HabitEvent) -> HabitProfile:
    """Return the living profile with the event applied."""
    if event.kind in {FeedbackKind.USER_CLOSE, FeedbackKind.STILLOPEN_CLOSE}:
        return observe_close(profile, event)
    if event.kind is FeedbackKind.CHAT:
        return profile

    host = _norm(event.host_suffix)
    if not host:
        return profile
    existing = profile.rule_for(host)
    before = _rule_snap(existing)
    if existing is None:
        rule = HabitRule(
            host_suffix=host,
            phrase=event.phrase,
            close_policy=_policy_for(event.kind),
            intention_override=event.to_intention,
            source=event.source or event.kind.value,
        )
        profile.rules.append(rule)
        existing = rule
    else:
        existing.hits += 1
        existing.phrase = event.phrase or existing.phrase
        existing.close_policy = _policy_for(event.kind)
        existing.source = event.source or event.kind.value
        if event.to_intention is not None:
            existing.intention_override = event.to_intention
        existing.touch()
    if event.kind in _KEEP_KINDS:
        stat = profile.stat_for(host)
        stat.kept += 1
        stat.last_action = event.kind.value
        stat.touch()
    append_mutation(
        profile,
        Mutation(
            kind=event.kind,
            source=event.source,
            summary=f"Keep {host} — learned from {event.kind.value}",
            host_suffix=host,
            before=before,
            after=_rule_snap(existing),
            phrase=event.phrase,
        ),
    )
    profile.touch()
    return profile


def observe_close(profile: HabitProfile, event: HabitEvent) -> HabitProfile:
    host = _norm(event.host_suffix)
    if not host:
        return profile
    stat = profile.stat_for(host)
    before = {
        "user_closed": stat.user_closed,
        "stillopen_closed": stat.stillopen_closed,
        "policy": profile.rule_for(host).close_policy.value if profile.rule_for(host) else None,
    }
    if event.kind is FeedbackKind.USER_CLOSE:
        stat.user_closed += 1
    else:
        stat.stillopen_closed += 1
    stat.last_action = event.kind.value
    stat.touch()

    keep = profile.rule_for(host)
    inferred = False
    if keep is None or keep.close_policy is ClosePolicy.FILE_THEN_CLOSE:
        should_infer = event.kind is FeedbackKind.STILLOPEN_CLOSE or (
            event.kind is FeedbackKind.USER_CLOSE and stat.user_closed >= _USER_CLOSE_INFER_AT
        )
        if should_infer and (keep is None or keep.close_policy is not ClosePolicy.ALWAYS_KEEP):
            if keep is None:
                keep = HabitRule(
                    host_suffix=host,
                    phrase=event.phrase,
                    close_policy=ClosePolicy.FILE_THEN_CLOSE,
                    source=event.kind.value,
                )
                profile.rules.append(keep)
            else:
                keep.close_policy = ClosePolicy.FILE_THEN_CLOSE
                keep.hits += 1
                keep.source = event.kind.value
                keep.phrase = event.phrase or keep.phrase
                keep.touch()
            inferred = True
    after = {
        "user_closed": stat.user_closed,
        "stillopen_closed": stat.stillopen_closed,
        "policy": profile.rule_for(host).close_policy.value if profile.rule_for(host) else None,
    }
    who = "you closed" if event.kind is FeedbackKind.USER_CLOSE else "you let Still Open close"
    summary = f"{who} {host}"
    if inferred:
        summary += " — now treated as ok to close when stale"
    append_mutation(
        profile,
        Mutation(
            kind=event.kind,
            source=event.source,
            summary=summary,
            host_suffix=host,
            before=before,
            after=after,
            phrase=event.phrase,
        ),
    )
    profile.touch()
    return profile


def upsert_rule(
    profile: HabitProfile,
    host: str,
    policy: ClosePolicy,
    *,
    phrase: str | None,
    source: str,
) -> HabitRule:
    host = _norm(host)
    existing = profile.rule_for(host)
    if existing is None:
        existing = HabitRule(
            host_suffix=host,
            phrase=phrase,
            close_policy=policy,
            source=source,
        )
        profile.rules.append(existing)
        return existing
    existing.hits += 1
    existing.close_policy = policy
    existing.phrase = phrase or existing.phrase
    existing.source = source
    existing.touch()
    return existing


def append_mutation(profile: HabitProfile, mutation: Mutation) -> None:
    profile.mutations.insert(0, mutation)
    profile.mutations = profile.mutations[:MAX_MUTATIONS]


def apply_habit_hint(tab: SanitizedTab, profile: HabitProfile, current: CloseHint) -> CloseHint:
    rule = profile.rule_for(tab.host)
    if rule is not None:
        return policy_to_hint(rule.close_policy)
    if tab.host_class.value in profile.close_classes:
        return CloseHint.PRE_CHECK
    return current


def set_cutoff(profile: HabitProfile, days: int, *, source: str, phrase: str | None = None) -> HabitProfile:
    before = profile.stale_cutoff_days
    profile.stale_cutoff_days = max(1, min(int(days), 90))
    if before == profile.stale_cutoff_days and source != "chat":
        return profile
    append_mutation(
        profile,
        Mutation(
            kind=FeedbackKind.CHAT if source == "chat" else FeedbackKind.KEEP,
            source=source,
            summary=f"Unused cutoff {before} → {profile.stale_cutoff_days} days",
            before={"stale_cutoff_days": before},
            after={"stale_cutoff_days": profile.stale_cutoff_days},
            phrase=phrase,
        ),
    )
    profile.touch()
    return profile


def keep_hosts(profile: HabitProfile) -> list[str]:
    return [
        rule.host_suffix
        for rule in profile.rules
        if rule.close_policy in {ClosePolicy.ALWAYS_KEEP, ClosePolicy.NEVER_CLOSE}
    ]


def close_ok_hosts(profile: HabitProfile) -> list[str]:
    return [
        rule.host_suffix
        for rule in profile.rules
        if rule.close_policy is ClosePolicy.FILE_THEN_CLOSE
    ]


def _policy_for(kind: FeedbackKind) -> ClosePolicy:
    if kind is FeedbackKind.UNDO:
        return ClosePolicy.NEVER_CLOSE
    return ClosePolicy.ALWAYS_KEEP


def _norm(host: str) -> str:
    return host.lower().removeprefix("www.").strip()


def _rule_snap(rule: HabitRule | None) -> dict[str, str | int | None]:
    if rule is None:
        return {"policy": None, "hits": 0}
    return {"policy": rule.close_policy.value, "hits": rule.hits}


__all__ = [
    "append_mutation",
    "apply_habit_hint",
    "close_ok_hosts",
    "keep_hosts",
    "mutate",
    "observe_close",
    "set_cutoff",
    "upsert_rule",
]
