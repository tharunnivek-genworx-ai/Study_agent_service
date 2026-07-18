"""Generation outcome types for graph routing, persistence, and API responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

GraphGenerationOutcome = Literal[
    "study_document",
    "reference_required",
    "vague_feedback",
    "malformed_document",
    "generator_error",
]

ApiGenerationOutcome = Literal[
    "deliverable",
    "reference_required",
    "vague_feedback",
    "malformed",
    "qc_failed",
    "generator_error",
]


class ActionRequiredOut(BaseModel):
    type: Literal["upload_reference", "clarify_feedback"]
    message: str
    topic_received: str | None = None
    reason: str | None = None


EXTERNAL_RESEARCH_FAIL_SOFT_MESSAGE = (
    "We couldn't find enough reliable information online for this topic, "
    "so this version was generated without external references. "
    "You can attach a reference PDF instead, or edit the generated content directly."
)


class GenerationOutcomeDetail(BaseModel):
    """Stored in JSONB and graph state for terminal non-deliverable outcomes."""

    message: str | None = None
    reason: str | None = None
    topic_received: str | None = None
    raw_preview: str | None = None
    external_research_fail_soft: bool | None = None
    fail_reason: str | None = None
