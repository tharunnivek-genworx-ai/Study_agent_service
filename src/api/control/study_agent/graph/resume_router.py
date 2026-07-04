"""Resume entry routing for study material generation graphs.

Handles cross-request checkpoint resume and within-run routing after
``study_agent`` and ``quality_check``.

After QC fail with retry mode in ``SECTION_RETRY_MODES`` or ``full_regeneration``,
``resolve_resume_next_node`` returns ``study_agent`` to continue the QC loop.
"""

from __future__ import annotations

from typing import Any, Literal

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.schemas.study_material_schemas.generation_outcome_schema import (
    GraphGenerationOutcome,
)
from src.api.utils.generation_progress.resume_helpers import (
    LAST_COMPLETED_NODE_KEY,
    RESUME_FLAG,
    coerce_datetime,
    coerce_uuid,
    is_resume_state,
    last_completed_node_from_state,
)
from src.api.utils.study_agent_utils.graph.node_helpers import SECTION_RETRY_MODES
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_GENERATOR_FORMAT_ATTEMPTS,
)

_TERMINAL_GENERATION_OUTCOMES: frozenset[GraphGenerationOutcome] = frozenset(
    {
        "reference_required",
        "vague_feedback",
        "generator_error",
    }
)


def route_after_study_agent(
    state: StudyMaterialGraphState,
) -> Literal["quality_check", "__end__", "study_agent"]:
    """Route after study_agent based on classified generation outcome."""
    if state.get("terminal_llm_failure") or state.get("error"):
        return "__end__"

    outcome = state.get("generation_outcome")
    if outcome == "study_document":
        return "quality_check"
    if outcome == "malformed_document":
        attempt = state.get("generator_format_attempt") or 0
        if attempt < MAX_GENERATOR_FORMAT_ATTEMPTS:
            return "study_agent"
        return "__end__"
    if outcome in _TERMINAL_GENERATION_OUTCOMES:
        return "__end__"
    if outcome is not None:
        return "__end__"

    # Legacy checkpoints without generation_outcome classification.
    if state.get("generated_content"):
        return "quality_check"
    return "study_agent"


def _is_terminal_generation_outcome(outcome: GraphGenerationOutcome | None) -> bool:
    if outcome is None:
        return False
    if outcome in _TERMINAL_GENERATION_OUTCOMES:
        return True
    if outcome == "malformed_document":
        return True
    return False


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
        next_node = route_after_study_agent(state)
        return next_node

    if last_completed_node == "quality_check":
        if _is_terminal_generation_outcome(state.get("generation_outcome")):
            return "__end__"

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
    "route_after_study_agent",
]
