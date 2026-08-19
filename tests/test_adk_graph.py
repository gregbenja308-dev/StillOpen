from stillopen_core.agents.adk_clerk import clerk_prompt
from stillopen_core.agents.conductor import propose_plan
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def test_clerk_prompt_excludes_blocked_hosts(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(user_id="local-dev", tabs=seeded_tabs, command="house")
    prompt = clerk_prompt(plan, sanitize_tabs(seeded_tabs))
    assert "chase.com" not in prompt.lower() or "blocked" in prompt
    # Chase is deny-listed — never appears as a source line
    assert "chase.com" not in prompt
