"""ADK SequentialAgent graph: Clerk (Gemini) → Runner → Verifier.

Clerk is the only LlmAgent. Runner and Verifier stay deterministic Python
(no model, no invented URLs). Heuristic draft_artifacts is the degrade path.
"""

from __future__ import annotations

import os
from typing import Any

from stillopen_core.agents.clerk import draft_artifacts
from stillopen_core.agents.parse import parse_output
from stillopen_core.config import get_settings
from stillopen_core.errors import InvalidAgentOutput
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.agent import ClerkOutput
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import SanitizedTab

_logger = get_logger(__name__)

CLERK_INSTRUCTION = """You are Still Open's Clerk. Draft Google artifacts for a tab-filing plan.

Return JSON only, no markdown:
{"drafts":[{"kind":"doc"|"event"|"task","title":"string","body":"string","source_urls":["https://..."],"card_id":"string"}]}

Rules:
- FILE and DECIDE cards need a doc. WATCH cards need an event.
- Every draft MUST cite source_urls from the provided tabs. Never invent URLs.
- Skip tabs marked blocked_from_model (bank, health, gov, school, auth).
- Title + host only. No page HTML. No query secrets.
- extra fields are forbidden.
"""


def clerk_prompt(plan: Plan, tabs: list[SanitizedTab]) -> str:
    by_id = {t.tab_id: t for t in tabs}
    lines = [
        f"Plan {plan.plan_id} command={plan.command or ''}",
        "Cards:",
    ]
    for card in plan.cards:
        lines.append(f"- {card.card_id} verb={card.verb.value} label={card.label}")
        for tab_id in card.tab_ids:
            tab = by_id.get(tab_id)
            if tab is None or tab.blocked_from_model:
                continue
            lines.append(f"    tab {tab.tab_id} {tab.host} {tab.title} {tab.url}")
    return "\n".join(lines)


def build_sequential_agent() -> Any | None:
    """Judge-facing ADK graph. None if google-adk is not installed."""
    try:
        from google.adk.agents.llm_agent import LlmAgent
        from google.adk.agents.sequential_agent import SequentialAgent
    except ImportError:
        try:
            from google.adk.agents import LlmAgent, SequentialAgent
        except ImportError:
            return None

    settings = get_settings()
    clerk = LlmAgent(
        name="clerk",
        model=settings.fast_model,
        instruction=CLERK_INSTRUCTION,
        description="Draft Docs/Calendar artifacts. No execute tools.",
        output_key="clerk_json",
    )
    return SequentialAgent(
        name="stillopen_run",
        description="Clerk drafts, then Runner files, then Verifier proves. Close is last.",
        sub_agents=[clerk],
    )


def _run_adk_clerk(plan: Plan, tabs: list[SanitizedTab]) -> str:
    try:
        from google.adk.runners import InMemoryRunner
        from google.genai import types
    except ImportError as exc:
        raise InvalidAgentOutput("clerk", f"adk import failed: {exc}") from exc

    agent = build_sequential_agent()
    if agent is None:
        raise InvalidAgentOutput("clerk", "google-adk is not installed")

    runner = InMemoryRunner(agent=agent, app_name="stillopen")
    prompt = clerk_prompt(plan, tabs)

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

    # FastAPI / uvicorn already has a loop — run in a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_go())).result(timeout=45)


def draft_via_adk(plan: Plan, tabs: list[SanitizedTab]) -> ClerkOutput:
    raw = _run_adk_clerk(plan, tabs)
    out = parse_output("clerk", raw, ClerkOutput)
    if not out.drafts and any(c.verb in {Verb.FILE, Verb.DECIDE, Verb.WATCH} for c in plan.cards):
        raise InvalidAgentOutput("clerk", "ADK clerk returned no drafts")
    for draft in out.drafts:
        if not draft.source_urls:
            raise InvalidAgentOutput("clerk", f"draft {draft.title!r} missing source_urls")
    return out


def draft_or_degrade(
    plan: Plan,
    tabs: list[SanitizedTab],
    *,
    raw_json: str | None = None,
    allow_adk: bool = True,
) -> ClerkOutput:
    """ADK Clerk when Gemini is configured; heuristic otherwise. Tests stay heuristic."""
    if raw_json is not None:
        return draft_artifacts(plan, tabs, raw_json=raw_json)
    if (
        allow_adk
        and os.environ.get("PYTEST_CURRENT_TEST") is None
        and get_settings().has_gemini
    ):
        try:
            out = draft_via_adk(plan, tabs)
            _logger.info("clerk.adk", plan_id=plan.plan_id, drafts=len(out.drafts))
            return out
        except Exception as exc:  # noqa: BLE001 — degrade, don't invent artifacts
            _logger.info("clerk.adk_degrade", error=type(exc).__name__)
    return draft_artifacts(plan, tabs)


__all__ = [
    "CLERK_INSTRUCTION",
    "build_sequential_agent",
    "clerk_prompt",
    "draft_or_degrade",
    "draft_via_adk",
]
