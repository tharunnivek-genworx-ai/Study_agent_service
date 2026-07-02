"""Resume entry routing for quiz generation graphs."""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.generation_progress.resume_helpers import (
    LAST_COMPLETED_NODE_KEY,
    RESUME_FLAG,
    coerce_datetime,
    coerce_uuid,
    coerce_uuid_list,
    is_resume_state,
    last_completed_node_from_state,
)
from src.api.utils.quiz_utils.graph.constants import QUESTION_RETRY_MODES

QUIZ_GRAPH_NODES = frozenset(
    {
        "load_generation_context",
        "load_existing_quiz_if_regenerate",
        "quiz_generator",
        "parse_quiz_output",
        "deterministic_validate",
        "quality_check",
        "persist_quiz_draft",
        "load_quiz_single_regen_context",
        "build_quiz_single_regen_prompt",
        "invoke_quiz_single_regen_llm",
        "parse_quiz_single_regen_output",
        "deterministic_validate_question_patches",
        "persist_question_patches",
    }
)


def is_question_rework_run(state: QuizGraphState) -> bool:
    if state.get("mode") == "improve":
        return True
    return bool(state.get("question_ids")) and state.get("mode") not in (
        "generate",
        "regenerate",
    )


def _resolve_generate_resume_next_node(
    state: QuizGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next generate/regenerate graph node after a cross-request resume."""
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


def _resolve_rework_resume_next_node(
    state: QuizGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next single-question rework graph node after a cross-request resume."""
    if not last_completed_node:
        return "load_quiz_single_regen_context"

    if last_completed_node == "load_quiz_single_regen_context":
        if not state.get("all_questions"):
            return "load_quiz_single_regen_context"
        return "build_quiz_single_regen_prompt"

    if last_completed_node == "build_quiz_single_regen_prompt":
        if state.get("prompt_input"):
            return "invoke_quiz_single_regen_llm"
        return "build_quiz_single_regen_prompt"

    if last_completed_node == "invoke_quiz_single_regen_llm":
        if state.get("terminal_llm_failure"):
            return "__end__"
        if state.get("error"):
            if state.get("raw_llm_output") and state.get("parsed_patches") is None:
                return "parse_quiz_single_regen_output"
            return "invoke_quiz_single_regen_llm"
        if state.get("parsed_patches") is not None:
            return "deterministic_validate_question_patches"
        if state.get("raw_llm_output"):
            return "parse_quiz_single_regen_output"
        return "invoke_quiz_single_regen_llm"

    if last_completed_node == "parse_quiz_single_regen_output":
        if state.get("error"):
            if state.get("raw_llm_output"):
                return "parse_quiz_single_regen_output"
            return "invoke_quiz_single_regen_llm"
        return "deterministic_validate_question_patches"

    if last_completed_node == "deterministic_validate_question_patches":
        if state.get("error"):
            return "__end__"
        if state.get("validated_patches"):
            return "persist_question_patches"
        return "invoke_quiz_single_regen_llm"

    if last_completed_node == "persist_question_patches":
        return "persist_question_patches"

    return "load_quiz_single_regen_context"


def resolve_resume_next_node(
    state: QuizGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next graph node after a cross-request resume."""
    if is_question_rework_run(state):
        return _resolve_rework_resume_next_node(
            state, last_completed_node=last_completed_node
        )
    return _resolve_generate_resume_next_node(
        state, last_completed_node=last_completed_node
    )


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
            state[key] = coerce_uuid(state[key])
        elif params.get(key):
            state[key] = coerce_uuid(params[key])

    if "mentor_id" in state:
        state["mentor_id"] = coerce_uuid(state["mentor_id"])
    elif params.get("mentor_id"):
        state["mentor_id"] = coerce_uuid(params["mentor_id"])

    if "question_ids" in state:
        state["question_ids"] = coerce_uuid_list(state["question_ids"])
    elif params.get("question_ids"):
        state["question_ids"] = coerce_uuid_list(params["question_ids"])

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
        ("question_count", "question_count"),
        ("difficulty", "difficulty"),
        ("mode", "mode"),
        ("mentor_feedback", "mentor_feedback"),
        ("quiz_id", "quiz_id"),
        ("node_id", "node_id"),
    ):
        if state_key not in state and params.get(param_key) is not None:
            value = params[param_key]
            if state_key in ("quiz_id", "node_id"):
                value = coerce_uuid(value)
            state[state_key] = value

    state[RESUME_FLAG] = True
    state[LAST_COMPLETED_NODE_KEY] = last_completed_node
    return state  # type: ignore[return-value]


__all__ = [
    "QUIZ_GRAPH_NODES",
    "hydrate_checkpoint_state",
    "is_question_rework_run",
    "is_resume_state",
    "last_completed_node_from_state",
    "resolve_resume_next_node",
]
