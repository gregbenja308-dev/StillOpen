import pytest
from stillopen_core.errors import ToolNotPermitted
from stillopen_core.gateway.router import AgentGateway


async def _ok() -> str:
    return "ok"


@pytest.mark.asyncio
async def test_clerk_cannot_create_doc() -> None:
    gw = AgentGateway()
    gw.register("create_doc", _ok)
    with pytest.raises(ToolNotPermitted):
        await gw.invoke(agent_name="clerk", tool_name="create_doc")


@pytest.mark.asyncio
async def test_runner_can_create_doc() -> None:
    gw = AgentGateway()
    gw.register("create_doc", _ok)
    assert await gw.invoke(agent_name="runner", tool_name="create_doc") == "ok"
