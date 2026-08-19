import pytest
from stillopen_core.agents.adk_clerk import clerk_prompt
from stillopen_core.agents.adk_graph import RUN_GRAPH, build_sequential_agent, graph_names
from stillopen_core.agents.conductor import propose_plan
from stillopen_core.memory.context import MAX_TABS_IN_PROMPT, prompt_tabs, rank_prompt_ids
from stillopen_core.memory.fakes import get_bank
from stillopen_core.memory.habits import mutate
from stillopen_core.schemas.habit import FeedbackKind, HabitEvent
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def test_run_graph_clerk_has_no_execute_tools() -> None:
    assert [node.name for node in RUN_GRAPH] == ["clerk", "runner", "verifier"]
    assert RUN_GRAPH[0].kind == "llm"
    assert RUN_GRAPH[0].tools == ()
    assert "create_doc" not in RUN_GRAPH[0].tools
    assert "create_doc" in RUN_GRAPH[1].tools
    assert RUN_GRAPH[1].kind == "python"
    assert RUN_GRAPH[2].kind == "python"
    assert graph_names() == ["clerk", "runner", "verifier"]


def test_sequential_agent_has_python_runner_and_verifier() -> None:
    agent = build_sequential_agent()
    if agent is None:
        pytest.skip("google-adk not installed")
    names = [sub.name for sub in agent.sub_agents]
    assert names == ["clerk", "runner", "verifier"]
    clerk, runner, verifier = agent.sub_agents
    assert list(getattr(clerk, "tools", []) or []) == []
    assert getattr(runner, "model", None) in (None, "")
    assert getattr(verifier, "model", None) in (None, "")


def test_clerk_prompt_excludes_blocked_hosts(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(user_id="local-dev", tabs=seeded_tabs, command="house")
    prompt = clerk_prompt(plan, sanitize_tabs(seeded_tabs))
    assert "chase.com" not in prompt.lower() or "blocked" in prompt
    assert "chase.com" not in prompt
    assert "super-secret" not in prompt
    assert "123456789" not in prompt


def test_clerk_prompt_caps_at_twelve() -> None:
    snaps = [
        TabSnapshot(
            tab_id=i,
            window_id=1,
            index=i,
            url=f"https://example.com/p/{i}",
            title=f"Page {i} notes",
        )
        for i in range(1, 21)
    ]
    plan = propose_plan(user_id="local-dev", tabs=snaps, command="file these notes")
    prompt = clerk_prompt(plan, sanitize_tabs(snaps))
    tab_lines = [line for line in prompt.splitlines() if line.strip().startswith("tab ")]
    assert len(tab_lines) <= MAX_TABS_IN_PROMPT


def test_clerk_prompt_includes_habit_pins(seeded_tabs: list[TabSnapshot]) -> None:
    bank = get_bank()
    profile = bank.habit_for("local-dev")
    mutate(
        profile,
        HabitEvent(kind=FeedbackKind.UNCHECK, host_suffix="redfin.com", phrase="keep listings"),
    )
    bank.put_habit(profile)
    plan = propose_plan(user_id="local-dev", tabs=seeded_tabs, command="house")
    prompt = clerk_prompt(plan, sanitize_tabs(seeded_tabs))
    assert "redfin.com:always_keep" in prompt


def test_rank_prompt_ids_pins_then_skips_bank(seeded_tabs: list[TabSnapshot]) -> None:
    tabs = sanitize_tabs(seeded_tabs)
    ranked = rank_prompt_ids(tabs, query="austin house", pin_ids=[11, 12, 16])
    assert 11 in ranked
    assert 12 in ranked
    assert 16 not in ranked
    clipped = prompt_tabs(tabs, ranked_ids=ranked)
    assert all(not t.blocked_from_model for t in clipped)
    assert 16 not in {t.tab_id for t in clipped}
