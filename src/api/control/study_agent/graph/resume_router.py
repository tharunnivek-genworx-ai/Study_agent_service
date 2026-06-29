"""Resume entry routing for study material generation graphs."""

from __future__ import annotations

from typing import Any

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.generation_progress.resume_helpers import (
    LAST_COMPLETED_NODE_KEY,
    RESUME_FLAG,
    coerce_datetime,
    coerce_uuid,
    is_resume_state,
    last_completed_node_from_state,
)
from src.api.utils.study_agent_utils.graph.node_helpers import SECTION_RETRY_MODES

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
            state[key] = coerce_uuid(state[key])
        elif params.get(key):
            state[key] = coerce_uuid(params[key])

    if "next_llm_retry_at" in state:
        state["next_llm_retry_at"] = coerce_datetime(state["next_llm_retry_at"])

    for param_key, state_key in (
        ("mentor_regeneration_goal", "mentor_feedback"),
        ("mentor_feedback", "mentor_feedback"),
        ("reference_material_id", "reference_material_id"),
    ):
        if state_key not in state and params.get(param_key) is not None:
            value = params[param_key]
            if state_key == "reference_material_id":
                value = coerce_uuid(value)
            state[state_key] = value

    state[RESUME_FLAG] = True
    state[LAST_COMPLETED_NODE_KEY] = last_completed_node
    return state  # type: ignore[return-value]


__all__ = [
    "STUDY_MATERIAL_GRAPH_NODES",
    "hydrate_checkpoint_state",
    "is_resume_state",
    "last_completed_node_from_state",
    "resolve_resume_next_node",
]
