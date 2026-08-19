"""Parse agent JSON into a schema; raise InvalidAgentOutput on failure."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from stillopen_core.errors import InvalidAgentOutput

_M = TypeVar("_M", bound=BaseModel)


def safe_parse_json(text: str) -> object:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


def parse_output(agent_name: str, text: str, schema: type[_M]) -> _M:
    try:
        payload = safe_parse_json(text)
    except json.JSONDecodeError as exc:
        raise InvalidAgentOutput(agent_name, f"invalid JSON: {exc.msg}") from exc
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise InvalidAgentOutput(agent_name, f"schema validation failed: {exc}") from exc


__all__ = ["parse_output", "safe_parse_json"]
