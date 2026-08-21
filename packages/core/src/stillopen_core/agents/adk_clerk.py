"""ADK Clerk: Gemini drafts, then Python File/verify. Heuristic is the degrade path."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from stillopen_core.agents.adk_graph import (
    CLERK_INSTRUCTION,
    RUN_GRAPH,
    build_clerk_llm_agent,
    build_sequential_agent,
)
from stillopen_core.agents.clerk import draft_artifacts, rewrite_copied_titles
from stillopen_core.agents.parse import parse_output
from stillopen_core.config import get_settings
from stillopen_core.errors import InvalidAgentOutput
from stillopen_core.gateway.gemini import TITLE_IS_DATA
from stillopen_core.gateway.router import AgentGateway, get_gateway
from stillopen_core.memory.context import habit_pins, prompt_tabs, rank_prompt_ids
from stillopen_core.memory.fakes import get_bank
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.agent import ClerkOutput
from stillopen_core.schemas.habit import HabitProfile
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import SanitizedTab

_logger = get_logger(__name__)

_ARTIFACT_VERBS = {Verb.FILE, Verb.DECIDE, Verb.WATCH}


def clerk_prompt(
    plan: Plan,
    tabs: list[SanitizedTab],
    *,
    profile: HabitProfile | None = None,
) -> str:
    if profile is None:
        profile = get_bank().habit_for(plan.user_id)
    pin_ids = [tid for card in plan.cards if card.verb in _ARTIFACT_VERBS for tid in card.tab_ids]
    query = " ".join(part for part in [plan.command, *[c.label for c in plan.cards]] if part)
    ranked = rank_prompt_ids(tabs, query=query, pin_ids=pin_ids)
    clipped = prompt_tabs(tabs, ranked_ids=ranked)
    by_id = {t.tab_id: t for t in clipped}
    lines = [
        f"{TITLE_IS_DATA}",
        f"Plan {plan.plan_id} command={plan.command or ''}",
    ]
    pins = habit_pins(profile)
    if pins:
        lines.append("Habit pins (learned keep/close; honor these):")
        for pin in pins:
            lines.append(f"  {pin}")
    lines.append("Cards:")
    for card in plan.cards:
        lines.append(f"- {card.card_id} verb={card.verb.value} label={card.label}")
        for tab_id in card.tab_ids:
            tab = by_id.get(tab_id)
            if tab is None:
                continue
            lines.append(
                f"    tab {tab.tab_id} {tab.host} url={_cite_url(tab.url)} title={tab.title!r}"
            )
    extra = [t for t in clipped if all(t.tab_id not in card.tab_ids for card in plan.cards)]
    if extra:
        lines.append("Other ranked tabs:")
        for tab in extra:
            lines.append(
                f"    tab {tab.tab_id} {tab.host} url={_cite_url(tab.url)} title={tab.title!r}"
            )
    return "\n".join(lines)


def _cite_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"[:160]


def _run_adk_clerk(plan: Plan, tabs: list[SanitizedTab], profile: HabitProfile | None) -> str:
    try:
        from google.adk.runners import InMemoryRunner  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]
    except ImportError as exc:
        raise InvalidAgentOutput("clerk", f"adk import failed: {exc}") from exc

    agent = build_clerk_llm_agent()
    if agent is None:
        raise InvalidAgentOutput("clerk", "google-adk is not installed")

    runner = InMemoryRunner(agent=agent, app_name="stillopen")
    prompt = clerk_prompt(plan, tabs, profile=profile)

    async def _go() -> str:
        session = await runner.session_service.create_session(
            app_name="stillopen",
            user_id=plan.user_id,
            session_id=plan.plan_id,
        )
        out = ""
        message = types.Content(role="user", parts=[types.Part(text=prompt)])
        async for event in runner.run_async(
            user_id=plan.user_id,
            session_id=session.id,
            new_message=message,
        ):
            if getattr(event, "content", None) and getattr(event.content, "parts", None):
                part = event.content.parts[0]
                if getattr(part, "text", None):
                    out = part.text
        return out

    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_go())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_go())).result(timeout=45)


def draft_via_adk(
    plan: Plan,
    tabs: list[SanitizedTab],
    *,
    profile: HabitProfile | None = None,
) -> ClerkOutput:
    raw = _run_adk_clerk(plan, tabs, profile)
    out = parse_output("clerk", raw, ClerkOutput)
    if not out.drafts and any(c.verb in _ARTIFACT_VERBS for c in plan.cards):
        raise InvalidAgentOutput("clerk", "ADK clerk returned no drafts")
    for draft in out.drafts:
        if not draft.source_urls:
            raise InvalidAgentOutput("clerk", f"draft {draft.title!r} missing source_urls")
    return rewrite_copied_titles(out, tabs, plan)


def draft_or_degrade(
    plan: Plan,
    tabs: list[SanitizedTab],
    *,
    raw_json: str | None = None,
    allow_adk: bool = True,
    gateway: AgentGateway | None = None,
    profile: HabitProfile | None = None,
) -> ClerkOutput:
    """ADK Clerk when Gemini is configured; heuristic otherwise. Tests stay heuristic."""
    gw = gateway or get_gateway()
    if profile is None:
        profile = get_bank().habit_for(plan.user_id)

    def _draft() -> ClerkOutput:
        if raw_json is not None:
            return draft_artifacts(plan, tabs, raw_json=raw_json)
        if (
            allow_adk
            and os.environ.get("PYTEST_CURRENT_TEST") is None
            and get_settings().has_gemini
        ):
            try:
                out = draft_via_adk(plan, tabs, profile=profile)
                _logger.info("clerk.adk", plan_id=plan.plan_id, drafts=len(out.drafts))
                return out
            except Exception as exc:  # noqa: BLE001 — degrade, don't invent artifacts
                _logger.info("clerk.adk_degrade", error=type(exc).__name__)
        return draft_artifacts(plan, tabs)

    return gw.invoke_sync(agent_name="clerk", tool_name="draft_artifact", fn=_draft)


__all__ = [
    "CLERK_INSTRUCTION",
    "RUN_GRAPH",
    "build_sequential_agent",
    "clerk_prompt",
    "draft_or_degrade",
    "draft_via_adk",
]
