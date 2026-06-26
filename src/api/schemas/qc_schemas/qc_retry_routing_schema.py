"""QC failure retry routing result."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RetryMode = Literal[
    "section_patch",
    "section_insert",
    "section_patch_then_insert",
    "full_regeneration",
    "none",
]


class RetryRoutingResult(BaseModel):
    mode: RetryMode
    failed_section_ids: list[str] = Field(default_factory=list)
    missing_checklist_ids: list[str] = Field(default_factory=list)
    section_failures: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""
