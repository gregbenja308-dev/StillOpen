"""Which agents may call which tools. Explicit on purpose."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    tool_name: str
    rate_limit_per_minute: int = 30

    def __post_init__(self) -> None:
        if self.rate_limit_per_minute < 1:
            raise ValueError(f"tool {self.tool_name!r}: rate limit must be positive")


@dataclass(frozen=True, slots=True)
class GatewayPolicy:
    tools_by_agent: dict[str, tuple[ToolPolicy, ...]] = field(default_factory=dict)

    def is_permitted(self, *, agent_name: str, tool_name: str) -> bool:
        return any(t.tool_name == tool_name for t in self.tools_by_agent.get(agent_name, ()))

    def tool_policy(self, *, agent_name: str, tool_name: str) -> ToolPolicy | None:
        for policy in self.tools_by_agent.get(agent_name, ()):
            if policy.tool_name == tool_name:
                return policy
        return None


_DEFAULT: Final[dict[str, tuple[ToolPolicy, ...]]] = {
    "surveyor": (ToolPolicy("sanitize_snapshot", rate_limit_per_minute=60),),
    "framer": (ToolPolicy("match_named_job", rate_limit_per_minute=30),),
    "clerk": (ToolPolicy("draft_artifact", rate_limit_per_minute=20),),
    "runner": (
        ToolPolicy("create_doc", rate_limit_per_minute=10),
        ToolPolicy("create_event", rate_limit_per_minute=10),
        ToolPolicy("create_task", rate_limit_per_minute=10),
        ToolPolicy("send_mail", rate_limit_per_minute=5),
        ToolPolicy("emit_tab_apply", rate_limit_per_minute=20),
    ),
    "verifier": (
        ToolPolicy("get_doc", rate_limit_per_minute=20),
        ToolPolicy("get_event", rate_limit_per_minute=20),
        ToolPolicy("write_undo", rate_limit_per_minute=20),
    ),
}


def load_default_policy() -> GatewayPolicy:
    return GatewayPolicy(tools_by_agent=dict(_DEFAULT))


__all__ = ["GatewayPolicy", "ToolPolicy", "load_default_policy"]
