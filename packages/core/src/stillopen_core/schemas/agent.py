"""Structured agent I/O. Extra fields forbidden — hallucinations cannot sneak through."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from stillopen_core.schemas.artifact import ArtifactDraft
from stillopen_core.schemas.base import StillOpenModel


class AgentOutputModel(StillOpenModel):
    """Permissive coercion for Gemini JSON; still forbid extra keys."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class ClerkOutput(AgentOutputModel):
    drafts: list[ArtifactDraft] = Field(default_factory=list)


class TabApply(AgentOutputModel):
    close_tab_ids: list[int] = Field(default_factory=list)
    keep_tab_ids: list[int] = Field(default_factory=list)


class VerifyReport(AgentOutputModel):
    artifacts_ok: bool
    apply_ok: bool
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


__all__ = ["AgentOutputModel", "ClerkOutput", "TabApply", "VerifyReport"]
