"""Map graph generation outcomes to API/persisted outcomes."""

from __future__ import annotations

from typing import Any

from src.api.schemas.study_material_schemas.generation_outcome_schema import (
    ApiGenerationOutcome,
    GraphGenerationOutcome,
)

_GRAPH_TO_API: dict[GraphGenerationOutcome, ApiGenerationOutcome] = {
    "reference_required": "reference_required",
    "vague_feedback": "vague_feedback",
    "malformed_document": "malformed",
    "generator_error": "generator_error",
}


def map_graph_to_api(
    outcome: GraphGenerationOutcome | None,
) -> ApiGenerationOutcome:
    """Map a graph routing outcome to its persisted API outcome."""
    if outcome is None:
        return "malformed"
    if outcome == "study_document":
        return "malformed"
    return _GRAPH_TO_API.get(outcome, "malformed")


def resolve_api_generation_outcome(
    graph_result: dict[str, Any],
) -> ApiGenerationOutcome:
    """Resolve the API generation outcome from a completed graph result."""
    graph_outcome = graph_result.get("generation_outcome")
    if graph_outcome != "study_document":
        return map_graph_to_api(graph_outcome)
    if graph_result.get("qc_evaluated") and graph_result.get("qc_passed"):
        return "deliverable"
    if graph_result.get("qc_evaluated"):
        return "qc_failed"
    return "malformed"
