"""Resume entry routing for hint generation graphs."""

from __future__ import annotations

from typing import Any

from src.api.control.hint_agent.states.hint_state import HintGraphState
from src.api.utils.generation_progress.resume_helpers import (
    LAST_COMPLETED_NODE_KEY,
    RESUME_FLAG,
    coerce_datetime,
    coerce_uuid,
    coerce_uuid_list,
    is_resume_state,
    last_completed_node_from_state,
)


def _pending_question_ids(
    questions: list[dict[str, Any]],
    hints_written: dict[str, Any],
) -> list[str]:
    """Return question IDs that still need validation or persistence."""
    written = set(hints_written.keys())
    return [q["question_id"] for q in questions if q["question_id"] not in written]


def resolve_resume_next_node(
    state: HintGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next graph node after a cross-request resume."""
    if not last_completed_node:
        return "load_hint_context"

    if last_completed_node == "load_hint_context":
        if not state.get("questions_for_hinting"):
            return "load_hint_context"
        return "build_hint_prompt_payload"

    if last_completed_node == "build_hint_prompt_payload":
        if state.get("prompt_input"):
            return "invoke_hint_llm"
        return "build_hint_prompt_payload"

    if last_completed_node == "invoke_hint_llm":
        if state.get("terminal_llm_failure"):
            return "persist_hint_failure_diagnostics"
        if state.get("error"):
            if state.get("raw_llm_output"):
                return "parse_hint_output"
            return "invoke_hint_llm"
        if state.get("raw_llm_output"):
            return "parse_hint_output"
        return "invoke_hint_llm"

    if last_completed_node == "parse_hint_output":
        if state.get("error"):
            if state.get("raw_llm_output"):
                return "parse_hint_output"
            return "invoke_hint_llm"
        return "validate_hint_quality"

    if last_completed_node == "validate_hint_quality":
        questions = state.get("questions_for_hinting") or []
        hints_written = state.get("hints_written") or {}
        failed_ids = state.get("failed_question_ids")
        if failed_ids:
            pending_failed = [qid for qid in failed_ids if qid not in hints_written]
            if pending_failed:
                return "validate_hint_quality"
        if _pending_question_ids(questions, hints_written):
            return "validate_hint_quality"
        return "persist_hints_to_questions"

    if last_completed_node == "persist_hints_to_questions":
        return "persist_hints_to_questions"

    if last_completed_node == "persist_hint_failure_diagnostics":
        return "persist_hint_failure_diagnostics"

    return "load_hint_context"


def hydrate_checkpoint_state(
    checkpoint_state: dict[str, Any],
    *,
    last_completed_node: str | None,
    request_params: dict[str, Any] | None = None,
) -> HintGraphState:
    """Build graph initial state from a persisted generation run checkpoint."""
    state: dict[str, Any] = dict(checkpoint_state)
    params = request_params or {}

    for key in ("node_id", "quiz_id", "space_id"):
        if key in state:
            state[key] = coerce_uuid(state[key])
        elif params.get(key):
            state[key] = coerce_uuid(params[key])

    if "mentor_id" in state:
        state["mentor_id"] = coerce_uuid(state["mentor_id"])
    elif params.get("mentor_id"):
        state["mentor_id"] = coerce_uuid(params["mentor_id"])

    if "questions_filter_ids" in state:
        state["questions_filter_ids"] = coerce_uuid_list(state["questions_filter_ids"])
    elif params.get("questions_filter_ids"):
        state["questions_filter_ids"] = coerce_uuid_list(params["questions_filter_ids"])

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
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
    "hydrate_checkpoint_state",
    "is_resume_state",
    "last_completed_node_from_state",
    "resolve_resume_next_node",
]
