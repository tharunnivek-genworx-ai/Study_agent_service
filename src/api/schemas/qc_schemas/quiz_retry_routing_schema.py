"""QC failure retry routing result for quiz generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

QuizRetryMode = Literal[
    "question_patch",
    "question_insert",
    "question_patch_then_insert",
    "full_regeneration",
    "none",
]


class QuizRetryRoutingResult(BaseModel):
    mode: QuizRetryMode
    failed_question_ids: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    question_failures: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""
