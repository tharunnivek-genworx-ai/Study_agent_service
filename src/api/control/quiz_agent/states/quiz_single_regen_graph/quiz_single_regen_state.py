"""TypedDict state for the quiz single-question regeneration LangGraph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID


class QuizSingleRegenGraphState(TypedDict, total=False):
    mentor_id: UUID
    node_id: UUID
    quiz_id: UUID
    space_id: UUID | None
    question_ids: list[UUID]
    mentor_feedback: str
    study_material_version_id: UUID | None
    study_material_content: str | None
    domain: str | None
    topic_split: list[dict] | None
    difficulty_profile: str | None
    node_title: str | None
    all_questions: list[dict[str, Any]] | None
    prompt_input: dict[str, str] | None
    raw_llm_output: str | None
    parsed_patches: list[dict[str, Any]] | None
    validated_patches: list[dict[str, Any]] | None
    hints_stale_question_ids: list[str]
    rework_status: str | None
    token_usage: int | None
    llm_model_used: str | None
    error: str | None

    terminal_llm_failure: bool
    llm_error_type: str | None
    provider_meta: dict[str, Any] | None
    next_llm_retry_at: datetime | None
    artifact_run_id: str | None

    _is_resume: bool
    _last_completed_node: str | None
