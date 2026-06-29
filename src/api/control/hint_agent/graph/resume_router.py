"""Resume entry routing for hint generation graphs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from src.api.control.hint_agent.states.hint_state import HintGraphState

_RESUME_FLAG = "_is_resume"
_LAST_COMPLETED_NODE_KEY = "_last_completed_node"


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


def _coerce_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


def _coerce_uuid_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [_coerce_uuid(item) for item in value]


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
) -> HintGraphState:
    """Build graph initial state from a persisted generation run checkpoint."""
    state: dict[str, Any] = dict(checkpoint_state)
    params = request_params or {}

    for key in ("node_id", "quiz_id", "space_id"):
        if key in state:
            state[key] = _coerce_uuid(state[key])
        elif params.get(key):
            state[key] = _coerce_uuid(params[key])

    if "mentor_id" in state:
        state["mentor_id"] = _coerce_uuid(state["mentor_id"])
    elif params.get("mentor_id"):
        state["mentor_id"] = _coerce_uuid(params["mentor_id"])

    if "questions_filter_ids" in state:
        state["questions_filter_ids"] = _coerce_uuid_list(state["questions_filter_ids"])
    elif params.get("questions_filter_ids"):
        state["questions_filter_ids"] = _coerce_uuid_list(
            params["questions_filter_ids"]
        )

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = _coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
        ("mentor_feedback", "mentor_feedback"),
        ("quiz_id", "quiz_id"),
        ("node_id", "node_id"),
    ):
        if state_key not in state and params.get(param_key) is not None:
            value = params[param_key]
            if state_key in ("quiz_id", "node_id"):
                value = _coerce_uuid(value)
            state[state_key] = value

    state[_RESUME_FLAG] = True
    state[_LAST_COMPLETED_NODE_KEY] = last_completed_node
    return state  # type: ignore[return-value]


def is_resume_state(state: HintGraphState) -> bool:
    return bool(state.get(_RESUME_FLAG))


def last_completed_node_from_state(state: HintGraphState) -> str | None:
    value = state.get(_LAST_COMPLETED_NODE_KEY)
    return str(value) if value else None
