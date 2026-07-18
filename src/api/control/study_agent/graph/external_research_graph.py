"""LangGraph subgraph for External Research Mode (design §2.3).

Internal sequence:
  cache_check → resolve_research_query → search → content_extraction
  → content_distillation → chunk_if_needed → knowledge_distillation
  → website_reduction → cross_website_merge → persist_cache_row
  → (success) attach_sources → assign extracted_reference_text

All LLM calls go through ``call_groq_with_rotation``.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from src.api.config import external_research_settings
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.data.repositories import NodeRepository
from src.api.data.repositories.study_agent_repositories.external_research_repository import (
    ExternalResearchRepository,
)
from src.api.utils.external_research_utils.abort import (
    abort_if_should_stop,
    build_should_continue_from_config,
)
from src.api.utils.external_research_utils.attach_sources import (
    attach_source_urls_to_node_media,
)
from src.api.utils.external_research_utils.chunking import chunk_cleaned_pages
from src.api.utils.external_research_utils.content_distillation import (
    distill_extracted_pages,
)
from src.api.utils.external_research_utils.content_extraction import (
    extract_pages_from_urls,
)
from src.api.utils.external_research_utils.cross_website_merge import (
    merge_website_summaries,
)
from src.api.utils.external_research_utils.knowledge_distillation import (
    distill_chunked_pages,
    extract_priority_concept_names,
)
from src.api.utils.external_research_utils.persist import (
    persist_external_research_cache,
)
from src.api.utils.external_research_utils.search import search_external_urls
from src.api.utils.external_research_utils.topic_resolution import (
    resolve_research_query,
)
from src.api.utils.external_research_utils.website_reduction import (
    reduce_distilled_pages,
)
from src.api.utils.generation_progress.reporter import maybe_report_node_enter

logger = logging.getLogger(__name__)

_compiled_external_research_graph = None

EXTERNAL_RESEARCH_INTERNAL_NODES = frozenset(
    {
        "external_research_cache_check",
        "external_research_resolve_query",
        "external_research_search",
        "external_research_content_extraction",
        "external_research_content_distillation",
        "external_research_chunk_if_needed",
        "external_research_knowledge_distillation",
        "external_research_website_reduction",
        "external_research_cross_website_merge",
        "external_research_persist_cache",
        "external_research_attach_sources",
    }
)


def _session_and_user(config: RunnableConfig) -> tuple[Any, UUID | None]:
    configurable = config.get("configurable") or {}
    session = configurable.get("session")
    user_raw = configurable.get("user_id")
    user_id = UUID(str(user_raw)) if user_raw else None
    return session, user_id


async def _report(config: RunnableConfig, node_name: str) -> None:
    from src.api.schemas import GenerationPipeline

    await maybe_report_node_enter(
        config,
        node_name,
        default_pipeline=GenerationPipeline.STUDY_MATERIAL,
    )


async def external_research_cache_check_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_cache_check")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    session, _user_id = _session_and_user(config)
    node_id = state.get("node_id")
    if session is None or node_id is None:
        return {
            "error": "session and node_id are required for external research cache check."
        }

    repo = ExternalResearchRepository(session)
    existing = await repo.get_by_node_id(node_id)
    if existing is None:
        return {"external_research_cache_hit": False}

    updates: dict[str, Any] = {
        "external_research_cache_hit": True,
        "external_research_status": existing.status,
        "external_research_fail_reason": existing.fail_reason,
        "external_research_query": existing.search_query_used,
        "resolved_topic": existing.resolved_topic,
        "resolved_subtopic": existing.resolved_subtopic,
        "knowledge_distillation_model_used": existing.knowledge_distillation_model_used,
    }
    if existing.status == "success" and existing.ground_truth_reference:
        updates["ground_truth_reference"] = existing.ground_truth_reference
        updates["external_source_urls"] = list(existing.source_urls or [])
        updates["extracted_reference_text"] = existing.ground_truth_reference
        updates["has_reference_material"] = True
    else:
        updates["ground_truth_reference"] = None
        updates["external_source_urls"] = []
        updates["extracted_reference_text"] = (
            state.get("extracted_reference_text") or ""
        )
    return updates


async def external_research_resolve_query_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_resolve_query")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    session, _user_id = _session_and_user(config)
    node_id = state.get("node_id")
    if session is None or node_id is None:
        return {"error": "session and node_id are required for query resolution."}

    node_repo = NodeRepository(session)
    node = await node_repo.get_node_by_id(node_id)
    if node is None:
        return {"error": f"Node not found: {node_id}"}

    ancestors = await node_repo.get_ancestors(node)  # root → parent
    nearest_first = list(reversed([cast(str, a.title) for a in ancestors if a.title]))
    node_title = state.get("node_title") or cast(str, node.title) or "topic"
    resolved = resolve_research_query(node_title, nearest_first)
    return {
        "node_title": node_title,
        "external_research_query": resolved["search_query"],
        "resolved_topic": resolved["resolved_topic"],
        "resolved_subtopic": resolved["resolved_subtopic"],
    }


async def external_research_search_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_search")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    # Use resolve_research_query topic+subtopic only — do not append checklist concepts.
    query = state.get("external_research_query") or state.get("node_title") or ""
    urls = search_external_urls(query)
    return {"search_result_urls": urls}


async def external_research_content_extraction_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_content_extraction")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    urls = list(state.get("search_result_urls") or [])
    target = external_research_settings.external_research_target_results
    # Walk the refill pool until we have ``target`` successful pages (or pool ends).
    extracted: list[dict[str, Any]] = []
    for url in urls:
        if len(extracted) >= target:
            break
        await abort_if_should_stop(should_continue)
        page_batch = extract_pages_from_urls([url])
        if not page_batch:
            logger.info("Extraction dropped URL; trying next search candidate: %s", url)
            continue
        extracted.extend(page_batch)

    updates: dict[str, Any] = {"extracted_pages": extracted}
    if not extracted:
        updates["external_research_status"] = "fail_soft"
        updates["external_research_fail_reason"] = "all_extractions_failed"
        updates["ground_truth_reference"] = None
        updates["external_source_urls"] = []
    return updates


async def external_research_content_distillation_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_content_distillation")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    cleaned = distill_extracted_pages(list(state.get("extracted_pages") or []))
    return {"cleaned_pages": cleaned}


async def external_research_chunk_if_needed_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_chunk_if_needed")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    chunked = chunk_cleaned_pages(list(state.get("cleaned_pages") or []))
    return {"chunked_pages": chunked}


async def external_research_knowledge_distillation_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_knowledge_distillation")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    priority = extract_priority_concept_names(
        list(state.get("must_cover_checklist") or [])
    )
    distilled, model = await distill_chunked_pages(
        list(state.get("chunked_pages") or []),
        domain=state.get("domain"),
        priority_concepts=priority,
        should_continue=should_continue,
    )
    updates: dict[str, Any] = {
        "distilled_pages": distilled,
        "knowledge_distillation_model_used": model,
    }
    if not distilled:
        updates["external_research_status"] = "fail_soft"
        updates["external_research_fail_reason"] = "all_extractions_failed"
        updates["ground_truth_reference"] = None
        updates["external_source_urls"] = []
    return updates


async def external_research_website_reduction_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_website_reduction")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    reduced = await reduce_distilled_pages(
        list(state.get("distilled_pages") or []),
        should_continue=should_continue,
    )
    updates: dict[str, Any] = {"reduced_pages": reduced}
    if not reduced:
        updates["external_research_status"] = "fail_soft"
        updates["external_research_fail_reason"] = "all_extractions_failed"
        updates["ground_truth_reference"] = None
        updates["external_source_urls"] = []
    return updates


async def external_research_cross_website_merge_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_cross_website_merge")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    priority = extract_priority_concept_names(
        list(state.get("must_cover_checklist") or [])
    )
    return await merge_website_summaries(
        list(state.get("reduced_pages") or []),
        priority_concepts=priority,
        should_continue=should_continue,
    )


async def external_research_persist_cache_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_persist_cache")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    session, user_id = _session_and_user(config)
    node_id = state.get("node_id")
    if session is None or node_id is None or user_id is None:
        return {
            "error": "session, node_id, and user_id are required to persist research cache."
        }

    node_repo = NodeRepository(session)
    node = await node_repo.get_node_by_id(node_id)
    if node is None:
        return {"error": f"Node not found: {node_id}"}

    status = state.get("external_research_status") or "fail_soft"
    ground_truth = state.get("ground_truth_reference")
    source_urls = list(state.get("external_source_urls") or [])

    await persist_external_research_cache(
        session,
        node_id=node_id,
        space_id=cast(UUID, node.space_id),
        mentor_id=user_id,
        status=status,
        fail_reason=state.get("external_research_fail_reason"),
        search_query_used=state.get("external_research_query"),
        resolved_topic=state.get("resolved_topic"),
        resolved_subtopic=state.get("resolved_subtopic"),
        ground_truth_reference=ground_truth if status == "success" else None,
        source_urls=source_urls if status == "success" else [],
        per_website_summary_count=len(state.get("reduced_pages") or []),
        knowledge_distillation_model_used=state.get(
            "knowledge_distillation_model_used"
        ),
    )

    updates: dict[str, Any] = {}
    if status == "success" and ground_truth:
        updates["extracted_reference_text"] = ground_truth
        updates["has_reference_material"] = True
    else:
        updates["extracted_reference_text"] = (
            state.get("extracted_reference_text") or ""
        )
    return updates


async def external_research_attach_sources_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    await _report(config, "external_research_attach_sources")
    should_continue = build_should_continue_from_config(config)
    await abort_if_should_stop(should_continue)

    if state.get("external_research_status") != "success":
        return {}

    session, user_id = _session_and_user(config)
    node_id = state.get("node_id")
    if session is None or node_id is None or user_id is None:
        return {}

    node_repo = NodeRepository(session)
    node = await node_repo.get_node_by_id(node_id)
    if node is None:
        return {}

    await attach_source_urls_to_node_media(
        session,
        node_id=node_id,
        space_id=cast(UUID, node.space_id),
        mentor_id=user_id,
        status=state.get("external_research_status"),
        source_urls=list(state.get("external_source_urls") or []),
    )
    return {}


def _route_after_cache_check(
    state: StudyMaterialGraphState,
) -> Literal["external_research_resolve_query", "__end__"]:
    if state.get("error"):
        return "__end__"
    if state.get("external_research_cache_hit"):
        return "__end__"
    return "external_research_resolve_query"


def _route_after_extraction(
    state: StudyMaterialGraphState,
) -> Literal[
    "external_research_content_distillation", "external_research_persist_cache"
]:
    if state.get("external_research_status") == "fail_soft":
        return "external_research_persist_cache"
    return "external_research_content_distillation"


def _route_after_knowledge(
    state: StudyMaterialGraphState,
) -> Literal["external_research_website_reduction", "external_research_persist_cache"]:
    if state.get("external_research_status") == "fail_soft":
        return "external_research_persist_cache"
    return "external_research_website_reduction"


def _route_after_reduction(
    state: StudyMaterialGraphState,
) -> Literal[
    "external_research_cross_website_merge",
    "external_research_persist_cache",
]:
    if state.get("external_research_status") == "fail_soft":
        return "external_research_persist_cache"
    return "external_research_cross_website_merge"


def _route_after_persist(
    state: StudyMaterialGraphState,
) -> Literal["external_research_attach_sources", "__end__"]:
    if state.get("error"):
        return "__end__"
    if state.get("external_research_status") == "success":
        return "external_research_attach_sources"
    return "__end__"


def build_external_research_graph() -> Any:
    """Build and compile the external research subgraph."""
    graph = StateGraph(StudyMaterialGraphState)

    graph.add_node("external_research_cache_check", external_research_cache_check_node)
    graph.add_node(
        "external_research_resolve_query",
        external_research_resolve_query_node,
    )
    graph.add_node("external_research_search", external_research_search_node)
    graph.add_node(
        "external_research_content_extraction",
        external_research_content_extraction_node,
    )
    graph.add_node(
        "external_research_content_distillation",
        external_research_content_distillation_node,
    )
    graph.add_node(
        "external_research_chunk_if_needed",
        external_research_chunk_if_needed_node,
    )
    graph.add_node(
        "external_research_knowledge_distillation",
        external_research_knowledge_distillation_node,
    )
    graph.add_node(
        "external_research_website_reduction",
        external_research_website_reduction_node,
    )
    graph.add_node(
        "external_research_cross_website_merge",
        external_research_cross_website_merge_node,
    )
    graph.add_node(
        "external_research_persist_cache", external_research_persist_cache_node
    )
    graph.add_node(
        "external_research_attach_sources",
        external_research_attach_sources_node,
    )

    graph.set_entry_point("external_research_cache_check")
    graph.add_conditional_edges(
        "external_research_cache_check",
        _route_after_cache_check,
        {
            "external_research_resolve_query": "external_research_resolve_query",
            "__end__": END,
        },
    )
    graph.add_edge("external_research_resolve_query", "external_research_search")
    graph.add_edge("external_research_search", "external_research_content_extraction")
    graph.add_conditional_edges(
        "external_research_content_extraction",
        _route_after_extraction,
        {
            "external_research_content_distillation": (
                "external_research_content_distillation"
            ),
            "external_research_persist_cache": "external_research_persist_cache",
        },
    )
    graph.add_edge(
        "external_research_content_distillation",
        "external_research_chunk_if_needed",
    )
    graph.add_edge(
        "external_research_chunk_if_needed",
        "external_research_knowledge_distillation",
    )
    graph.add_conditional_edges(
        "external_research_knowledge_distillation",
        _route_after_knowledge,
        {
            "external_research_website_reduction": "external_research_website_reduction",
            "external_research_persist_cache": "external_research_persist_cache",
        },
    )
    graph.add_conditional_edges(
        "external_research_website_reduction",
        _route_after_reduction,
        {
            "external_research_cross_website_merge": (
                "external_research_cross_website_merge"
            ),
            "external_research_persist_cache": "external_research_persist_cache",
        },
    )
    graph.add_edge(
        "external_research_cross_website_merge",
        "external_research_persist_cache",
    )
    graph.add_conditional_edges(
        "external_research_persist_cache",
        _route_after_persist,
        {
            "external_research_attach_sources": "external_research_attach_sources",
            "__end__": END,
        },
    )
    graph.add_edge("external_research_attach_sources", END)

    return graph.compile()


def get_external_research_graph() -> Any:
    global _compiled_external_research_graph
    if _compiled_external_research_graph is None:
        _compiled_external_research_graph = build_external_research_graph()
    return _compiled_external_research_graph


def reset_external_research_graph() -> None:
    """Clear the compiled subgraph cache (for tests)."""
    global _compiled_external_research_graph
    _compiled_external_research_graph = None
