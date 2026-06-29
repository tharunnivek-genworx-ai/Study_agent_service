"""Resume entry routing for study material generation graphs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.graph.node_helpers import SECTION_RETRY_MODES

_RESUME_FLAG = "_is_resume"
_LAST_COMPLETED_NODE_KEY = "_last_completed_node"

STUDY_MATERIAL_GRAPH_NODES = frozenset(
    {
        "resolver",
        "llamaparse",
        "concept_checklist",
        "study_agent",
        "quality_check",
    }
)


def resolve_resume_next_node(
    state: StudyMaterialGraphState,
    *,
    last_completed_node: str | None,
) -> str:
    """Return the next graph node after a cross-request resume."""
    if not last_completed_node:
        return "resolver"

    if last_completed_node == "resolver":
        if state.get("skip_llamaparse"):
            return "concept_checklist"
        if state.get("has_reference_material") and state.get("reference_file_path"):
            return "llamaparse"
        return "concept_checklist"

    if last_completed_node == "llamaparse":
        return "concept_checklist"

    if last_completed_node == "concept_checklist":
        if not state.get("must_cover_checklist"):
            return "concept_checklist"
        return "study_agent"

    if last_completed_node == "study_agent":
        if state.get("generated_content"):
            return "quality_check"
        return "study_agent"

    if last_completed_node == "quality_check":
        qc_result = state.get("qc_result") or {}
        if isinstance(qc_result, dict) and qc_result.get("qcInfraError"):
            return "quality_check"

        retry_mode = state.get("qc_retry_mode") or "none"
        if retry_mode in SECTION_RETRY_MODES or retry_mode == "full_regeneration":
            return "study_agent"
        if state.get("generated_content"):
            return "quality_check"

    return "resolver"


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
) -> StudyMaterialGraphState:
    """Build graph initial state from a persisted generation run checkpoint."""
    state: dict[str, Any] = dict(checkpoint_state)
    params = request_params or {}

    for key in ("node_id", "reference_material_id"):
        if key in state:
            state[key] = _coerce_uuid(state[key])
        elif params.get(key):
            state[key] = _coerce_uuid(params[key])

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = _coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
        ("mentor_regeneration_goal", "mentor_feedback"),
        ("mentor_feedback", "mentor_feedback"),
        ("reference_material_id", "reference_material_id"),
    ):
        if state_key not in state and params.get(param_key) is not None:
            value = params[param_key]
            if state_key == "reference_material_id":
                value = _coerce_uuid(value)
            state[state_key] = value

    state[_RESUME_FLAG] = True
    state[_LAST_COMPLETED_NODE_KEY] = last_completed_node
    return state  # type: ignore[return-value]


def is_resume_state(state: StudyMaterialGraphState) -> bool:
    return bool(state.get(_RESUME_FLAG))


def last_completed_node_from_state(state: StudyMaterialGraphState) -> str | None:
    value = state.get(_LAST_COMPLETED_NODE_KEY)
    return str(value) if value else None
