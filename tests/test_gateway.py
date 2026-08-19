import pytest
from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.run_conductor import run_plan
from stillopen_core.errors import ToolNotPermitted
from stillopen_core.gateway.policies import GatewayPolicy, ToolPolicy
from stillopen_core.gateway.router import AgentGateway
from stillopen_core.schemas.plan import PlanStatus
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


async def _ok() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_clerk_cannot_create_doc() -> None:
    gw = AgentGateway()
    gw.register("create_doc", _ok)
    with pytest.raises(ToolNotPermitted):
        await gw.invoke(agent_name="clerk", tool_name="create_doc")


def test_clerk_cannot_create_doc_on_sync_path() -> None:
    gw = AgentGateway()
    with pytest.raises(ToolNotPermitted):
        gw.invoke_sync(agent_name="clerk", tool_name="create_doc", fn=lambda: "nope")


@pytest.mark.asyncio
async def test_runner_can_create_doc() -> None:
    gw = AgentGateway()
    gw.register("create_doc", _ok)
    assert await gw.invoke(agent_name="runner", tool_name="create_doc") == "ok"


def test_run_plan_gateway_denies_runner_create_doc(seeded_tabs: list[TabSnapshot]) -> None:
    house = [t for t in seeded_tabs if t.tab_id in {11, 12, 13}]
    plan = propose_plan(
        user_id="local-dev",
        tabs=house,
        command="house shopping",
        force_file=True,
    )
    gw = AgentGateway(
        GatewayPolicy(
            tools_by_agent={
                "clerk": (ToolPolicy("draft_artifact"),),
                "runner": (ToolPolicy("emit_tab_apply"),),
                "verifier": (ToolPolicy("get_doc"), ToolPolicy("get_event")),
            }
        )
    )
    result = run_plan(plan, sanitize_tabs(house), gateway=gw)
    assert result.plan.status is PlanStatus.DEGRADED
    assert result.report.artifacts_ok is False
    assert result.apply.close_tab_ids == []

