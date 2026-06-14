"""Entry point for running the study material generation LangGraph."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.agents.study_material.graph import get_study_material_graph
from src.api.core.agents.study_material.state import StudyMaterialGraphState
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (  # noqa: E501
    LLMGenerationFailedException,
    StudyMaterialReferenceCacheMissingException,
)
from src.api.data.repositories.study_agent_repositories.reference_material_repository import (  # noqa: E501
    ReferenceMaterialRepository,
)
from src.api.utils.study_agent_utils.reference_cache import load_reference_cache

logger = logging.getLogger(__name__)


async def _load_cached_reference(
    session: AsyncSession,
    reference_material_id: UUID | None,
) -> tuple[str, dict]:
    """Load formatted reference text from disk cache (no LlamaParse)."""
    if reference_material_id is None:
        return "", {}

    repo = ReferenceMaterialRepository(session)
    material = await repo.get_by_id(reference_material_id)
    if material is None or material.deleted_at is not None:
        return "", {}

    cached = load_reference_cache(material.file_url, reference_material_id)
    if cached is None:
        raise StudyMaterialReferenceCacheMissingException()
    return cached


def _cleanup_temp_reference(result: StudyMaterialGraphState) -> None:
    reference_path = result.get("reference_file_path")
    if reference_path and result.get("reference_file_is_temp"):
        path = Path(reference_path)
        if path.exists() and path.is_file():
            try:
                os.remove(path)
            except OSError:
                pass


async def _run_graph(
    session: AsyncSession,
    initial_state: StudyMaterialGraphState,
) -> StudyMaterialGraphState:
    graph = get_study_material_graph()
    result: StudyMaterialGraphState = await graph.ainvoke(
        initial_state,
        config={"configurable": {"session": session}},
    )

    _cleanup_temp_reference(result)

    if result.get("error"):
        detail = str(result["error"])
        logger.error("Study material generation failed: %s", detail)
        raise LLMGenerationFailedException(detail=detail)

    if not result.get("generated_content"):
        logger.error("Study material generation completed without content.")
        raise LLMGenerationFailedException(
            detail="Study material generation completed without content."
        )

    return result


async def run_study_material_generation(
    session: AsyncSession,
    node_id: UUID,
    reference_material_id: UUID | None = None,
) -> StudyMaterialGraphState:
    """First-time generate: resolver → optional llamaparse → study_agent."""
    initial_state: StudyMaterialGraphState = {
        "node_id": node_id,
        "reference_material_id": reference_material_id,
        "generation_mode": "generate",
        "skip_llamaparse": False,
    }
    return await _run_graph(session, initial_state)


async def run_study_material_regeneration(
    session: AsyncSession,
    node_id: UUID,
    current_draft_content: str,
    mentor_regeneration_goal: str,
    reference_material_id: UUID | None,
) -> StudyMaterialGraphState:
    """Regenerate from active draft + mentor feedback. Skips LlamaParse when cached."""
    extracted_text = ""
    parsed_data: dict = {}
    skip_llamaparse = False

    if reference_material_id is not None:
        extracted_text, parsed_data = await _load_cached_reference(
            session, reference_material_id
        )
        skip_llamaparse = True

    initial_state: StudyMaterialGraphState = {
        "node_id": node_id,
        "reference_material_id": reference_material_id,
        "generation_mode": "regenerate",
        "skip_llamaparse": skip_llamaparse,
        "current_draft_content": current_draft_content,
        "mentor_feedback": mentor_regeneration_goal,
        "extracted_reference_text": extracted_text,
        "parsed_reference_data": parsed_data,
    }
    return await _run_graph(session, initial_state)


async def run_study_material_improve(
    session: AsyncSession,
    node_id: UUID,
    current_draft_content: str,
    mentor_feedback: str,
    reference_material_id: UUID | None,
) -> StudyMaterialGraphState:
    """Improve active draft surgically. Skips LlamaParse when cached reference exists."""
    extracted_text = ""
    parsed_data: dict = {}
    skip_llamaparse = False

    if reference_material_id is not None:
        extracted_text, parsed_data = await _load_cached_reference(
            session, reference_material_id
        )
        skip_llamaparse = True

    initial_state: StudyMaterialGraphState = {
        "node_id": node_id,
        "reference_material_id": reference_material_id,
        "generation_mode": "improve",
        "skip_llamaparse": skip_llamaparse,
        "current_draft_content": current_draft_content,
        "mentor_feedback": mentor_feedback,
        "extracted_reference_text": extracted_text,
        "parsed_reference_data": parsed_data,
    }
    return await _run_graph(session, initial_state)
