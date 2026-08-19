"""In-process Agent Gateway — allowlist + rate limit."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from stillopen_core.errors import AgentUnavailable, RateLimitExceeded, ToolNotPermitted
from stillopen_core.gateway.policies import GatewayPolicy, load_default_policy
from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)

ToolHandler = Callable[..., Awaitable[Any]]


class AgentGateway:
    def __init__(self, policy: GatewayPolicy | None = None) -> None:
        self._policy = policy or load_default_policy()
        self._handlers: dict[str, ToolHandler] = {}
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        if tool_name in self._handlers:
            raise ValueError(f"tool already registered: {tool_name!r}")
        self._handlers[tool_name] = handler

    async def invoke(self, *, agent_name: str, tool_name: str, **kwargs: Any) -> Any:
        if not self._policy.is_permitted(agent_name=agent_name, tool_name=tool_name):
            _logger.info("gateway.denied", agent=agent_name, tool=tool_name)
            raise ToolNotPermitted(agent_name=agent_name, tool_name=tool_name)
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise AgentUnavailable(f"tool {tool_name!r} is not registered")
        policy = self._policy.tool_policy(agent_name=agent_name, tool_name=tool_name)
        assert policy is not None
        now = time.monotonic()
        window = self._windows[(agent_name, tool_name)]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= policy.rate_limit_per_minute:
            raise RateLimitExceeded(agent_name, tool_name, policy.rate_limit_per_minute)
        window.append(now)
        return await handler(**kwargs)


__all__ = ["AgentGateway"]
