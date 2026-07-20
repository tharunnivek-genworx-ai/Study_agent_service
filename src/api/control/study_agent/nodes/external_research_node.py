"""Invoke the external research subgraph as a single parent-graph node."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.api.control.study_agent.graph.external_research_graph import (
    get_external_research_graph,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.generation_progress.reporter import maybe_report_node_enter

logger = logging.getLogger(__name__)

_RESULT_KEYS = (
    "external_research_cache_hit",
    "external_research_status",
    "external_research_fail_reason",
    "external_research_query",
    "resolved_topic",
    "resolved_subtopic",
    "external_source_urls",
    "external_video_urls",
    "youtube_attach_status",
    "youtube_fail_reason",
    "external_research_youtube_backfill_only",
    "ground_truth_reference",
    "extracted_reference_text",
    "has_reference_material",
    "knowledge_distillation_model_used",
    "search_result_urls",
    "extracted_pages",
    "cleaned_pages",
    "chunked_pages",
    "distilled_pages",
    "reduced_pages",
    "error",
    "node_title",
)


async def external_research_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Run the compiled external_research subgraph and return state updates."""
    from src.api.schemas import GenerationPipeline

    await maybe_report_node_enter(
        config,
        "external_research",
        default_pipeline=GenerationPipeline.STUDY_MATERIAL,
    )

    subgraph = get_external_research_graph()
    result = await subgraph.ainvoke(dict(state), config)
    if not isinstance(result, dict):
        logger.error("External research subgraph returned non-dict result")
        return {"error": "External research subgraph failed."}

    updates: dict[str, Any] = {}
    for key in _RESULT_KEYS:
        if key in result:
            updates[key] = result[key]
    return updates
