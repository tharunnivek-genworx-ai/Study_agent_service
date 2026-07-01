"""TypedDict state definitions for the quiz and hint generation LangGraphs.

Both state classes are plain ``TypedDict`` (no Pydantic, no dataclasses) and use
``total=False`` so individual nodes may return partial updates that LangGraph
merges into the running state.
"""

from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID


class QuizGraphState(TypedDict, total=False):
    mentor_id: UUID
    space_id: UUID | None
    node_id: UUID
    mode: str  # "generate" or "regenerate"
    quiz_id: UUID | None  # required for regenerate
    question_count: int
    difficulty: str
    mentor_feedback: str | None
    node_title: str | None
    study_material_version_id: UUID | None
    study_material_content: str | None
    domain: str | None
    topic_split: list[dict] | None
    existing_quiz_questions: list | None  # populated only in regenerate mode
    prompt_input: dict | None
    raw_llm_output: str | None
    parsed_questions: list | None
    validated_questions: list | None
    hints_stale_question_ids: list[str]
    struct_validation_passed: bool

    # Pre-QC deterministic retry
    gen_attempt: int
    gen_feedback: str

    # QC retry routing (mirrors study agent)
    qc_retry_mode: str
    qc_frozen_question_ids: list[str]
    qc_reverify_question_ids: list[str]
    qc_missing_concepts: list[str]
    qc_question_failures: list[dict]
    fixed_questions: list[dict] | None
    qc_verification_mode: str  # "full" | "targeted"
    quiz_title: str | None
    created_quiz_id: UUID | None
    llm_model_used: str | None
    token_usage: int | None
    error: str | None

    # ── Quality-Check fields ──────────────────────────────────────
    qc_passed: bool  # True when QC evaluation passed
    qc_result: dict[str, Any] | None  # Full parsed JSON report from QC LLM
    qc_feedback: str  # Formatted QC issues for the retry prompt
    qc_attempt: int  # Number of QC evaluations so far (max 3)
    qc_failed_permanently: bool  # True when all 3 QC attempts failed
    failed_qc_feedback: str | None  # Previously failed QC feedback context from DB

    # ── LLM failure diagnostics ───────────────────────────────────
    terminal_llm_failure: bool
    llm_error_type: str | None
    provider_meta: dict[str, Any] | None
    next_llm_retry_at: datetime | None
    artifact_run_id: str | None

    # Resume routing (cross-request checkpoint restore)
    _is_resume: bool
    _last_completed_node: str | None
