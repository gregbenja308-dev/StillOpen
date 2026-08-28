"""``GET /v1/agents/registry`` — the Agent Registry for this deployment.

Judges can point at a single endpoint to see which agents are wired up,
what tools each is permitted to call, and which agent is the LLM.
The registry reads ``RUN_GRAPH`` and the current ``GatewayPolicy`` so it
cannot drift from the code.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from stillopen_core.agents.adk_graph import RUN_GRAPH, build_sequential_agent
from stillopen_core.config import get_settings
from stillopen_core.gateway.policies import load_default_policy

router = APIRouter(prefix="/v1/agents", tags=["registry"])


class AgentDescriptor(BaseModel):
    name: str
    kind: str
    tools: list[str]
    description: str
    model: str = ""
    rate_limits_per_minute: dict[str, int] = Field(default_factory=dict)


class RegistryResponse(BaseModel):
    graph: str
    fast_model: str
    reasoning_model: str
    armor: str
    agents: list[AgentDescriptor]


@router.get("/registry", response_model=RegistryResponse)
def registry() -> RegistryResponse:
    settings = get_settings()
    policy = load_default_policy()
    agents: list[AgentDescriptor] = []
    graph = build_sequential_agent()
    graph_models = {sub.name: getattr(sub, "model", "") for sub in getattr(graph, "sub_agents", [])}
    for node in RUN_GRAPH:
        limits = {
            t.tool_name: t.rate_limit_per_minute
            for t in policy.tools_by_agent.get(node.name, ())
        }
        model = ""
        if node.kind == "llm":
            model = graph_models.get(node.name) or settings.fast_model
        agents.append(
            AgentDescriptor(
                name=node.name,
                kind=node.kind,
                tools=list(node.tools),
                description=node.description,
                model=model,
                rate_limits_per_minute=limits,
            )
        )
    return RegistryResponse(
        graph=">".join(a.name for a in agents),
        fast_model=settings.fast_model,
        reasoning_model=settings.reasoning_model,
        armor=settings.armor_backend,
        agents=agents,
    )


__all__ = ["router"]
