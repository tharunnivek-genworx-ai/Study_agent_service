"""Resume entry routing for quiz generation graphs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from src.api.control.quiz_agent.states.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.graph.constants import QUESTION_RETRY_MODES

_RESUME_FLAG = "_is_resume"
_LAST_COMPLETED_NODE_KEY = "_last_completed_node"

QUIZ_GRAPH_NODES = frozenset(
    {
        "load_generation_context",
        "load_existing_quiz_if_regenerate",
        "quiz_generator",
        "parse_quiz_output",
        "deterministic_validate",
        "quality_check",
        "persist_quiz_draft",
    }
)


def resolve_resume_next_node(
    state: QuizGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next graph node after a cross-request resume."""
    if not last_completed_node:
        return "load_generation_context"

    if last_completed_node == "load_generation_context":
        if not state.get("study_material_content"):
            return "load_generation_context"
        if state.get("mode") == "regenerate" and not state.get(
            "existing_quiz_questions"
        ):
            return "load_existing_quiz_if_regenerate"
        return "quiz_generator"

    if last_completed_node == "load_existing_quiz_if_regenerate":
        return "quiz_generator"

    if last_completed_node == "quiz_generator":
        if state.get("terminal_llm_failure"):
            return "persist_quiz_draft"
        if state.get("error"):
            if state.get("raw_llm_output") and state.get("parsed_questions") is None:
                return "parse_quiz_output"
            return "quiz_generator"
        if state.get("validated_questions") is not None:
            return "deterministic_validate"
        if state.get("parsed_questions") is not None:
            return "deterministic_validate"
        if state.get("raw_llm_output"):
            return "parse_quiz_output"
        return "quiz_generator"

    if last_completed_node == "parse_quiz_output":
        if state.get("error"):
            if state.get("raw_llm_output"):
                return "parse_quiz_output"
            return "quiz_generator"
        return "deterministic_validate"

    if last_completed_node == "deterministic_validate":
        if state.get("struct_validation_passed"):
            return "quality_check"
        if state.get("qc_failed_permanently"):
            return "persist_quiz_draft"
        return "quiz_generator"

    if last_completed_node == "quality_check":
        if state.get("qc_passed") or state.get("qc_failed_permanently"):
            return "persist_quiz_draft"

        qc_result = state.get("qc_result") or {}
        if isinstance(qc_result, dict) and qc_result.get("qcInfraError"):
            return "quality_check"

        retry_mode = state.get("qc_retry_mode") or "none"
        if retry_mode in QUESTION_RETRY_MODES or retry_mode == "full_regeneration":
            return "quiz_generator"
        if state.get("validated_questions"):
            return "quality_check"

    if last_completed_node == "persist_quiz_draft":
        return "persist_quiz_draft"

    return "load_generation_context"


def _coerce_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


def _coerce_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def hydrate_checkpoint_state(
    checkpoint_state: dict[str, Any],
    *,
    last_completed_node: str | None,
    request_params: dict[str, Any] | None = None,
) -> QuizGraphState:
    """Build graph initial state from a persisted generation run checkpoint."""
    state: dict[str, Any] = dict(checkpoint_state)
    params = request_params or {}

    for key in ("node_id", "quiz_id", "study_material_version_id", "space_id"):
        if key in state:
            state[key] = _coerce_uuid(state[key])
        elif params.get(key):
            state[key] = _coerce_uuid(params[key])

    if "mentor_id" in state:
        state["mentor_id"] = _coerce_uuid(state["mentor_id"])
    elif params.get("mentor_id"):
        state["mentor_id"] = _coerce_uuid(params["mentor_id"])

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = _coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
        ("question_count", "question_count"),
        ("difficulty", "difficulty"),
        ("mode", "mode"),
        ("mentor_feedback", "mentor_feedback"),
        ("quiz_id", "quiz_id"),
    ):
        if state_key not in state and params.get(param_key) is not None:
            value = params[param_key]
            if state_key == "quiz_id":
                value = _coerce_uuid(value)
            state[state_key] = value

    state[_RESUME_FLAG] = True
    state[_LAST_COMPLETED_NODE_KEY] = last_completed_node
    return state  # type: ignore[return-value]


def is_resume_state(state: QuizGraphState) -> bool:
    return bool(state.get(_RESUME_FLAG))


def last_completed_node_from_state(state: QuizGraphState) -> str | None:
    value = state.get(_LAST_COMPLETED_NODE_KEY)
    return str(value) if value else None
