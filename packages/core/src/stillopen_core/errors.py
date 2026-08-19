"""Domain exceptions. Unexpected ``Exception``s are bugs."""

from __future__ import annotations


class StillOpenError(Exception):
    """Base class for every Still Open-specific error."""


class ConfigError(StillOpenError):
    """Runtime environment is misconfigured."""


class GuardrailBlocked(StillOpenError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TokenPersistDenied(StillOpenError):
    """No Fernet key configured; refusing to write OAuth tokens to disk."""


class AgentError(StillOpenError):
    pass


class InvalidAgentOutput(AgentError):
    def __init__(self, agent_name: str, validation_error: str) -> None:
        super().__init__(f"agent {agent_name!r} produced invalid output: {validation_error}")
        self.agent_name = agent_name
        self.validation_error = validation_error


class AgentUnavailable(AgentError):
    pass


class GatewayError(StillOpenError):
    pass


class ToolNotPermitted(GatewayError):
    def __init__(self, agent_name: str, tool_name: str) -> None:
        super().__init__(f"agent {agent_name!r} may not call tool {tool_name!r}")
        self.agent_name = agent_name
        self.tool_name = tool_name


class RateLimitExceeded(GatewayError):
    def __init__(self, agent_name: str, tool_name: str, limit: int) -> None:
        super().__init__(
            f"agent {agent_name!r} exceeded rate limit for {tool_name!r} (limit={limit})"
        )
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.limit = limit


class NotFound(StillOpenError):
    def __init__(self, collection: str, doc_id: str) -> None:
        super().__init__(f"{collection}/{doc_id} not found")
        self.collection = collection
        self.doc_id = doc_id


__all__ = [
    "AgentError",
    "AgentUnavailable",
    "ConfigError",
    "GatewayError",
    "GuardrailBlocked",
    "InvalidAgentOutput",
    "NotFound",
    "RateLimitExceeded",
    "StillOpenError",
    "TokenPersistDenied",
    "ToolNotPermitted",
]
