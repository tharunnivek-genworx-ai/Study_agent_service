# src/api/control/study_agent/graph/runner.py
"""Entry point for running the study material generation LangGraph."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.study_agent.graph.graph import get_study_material_graph
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.core.exceptions import (  # noqa: E501
    LLMGenerationFailedException,
    StudyMaterialReferenceParseMissingException,
)
from src.api.data.repositories import (  # noqa: E501
    ReferenceLlamaParseRepository,
)
from src.api.utils.generation_progress import (
    GenerationPipeline,
    invoke_graph_with_progress,
)
from src.api.utils.reference_llamaparse_utils.reference_llamaparse_persistence import (
    build_parsed_reference_data,
)

logger = logging.getLogger(__name__)


async def _load_persisted_reference(
    session: AsyncSession,
    reference_material_id: UUID | None,
    node_id: UUID,
) -> tuple[str, dict]:
    """Load formatted reference text and structured data from the database."""
    if reference_material_id is None:
        return "", {}

    repo = ReferenceLlamaParseRepository(session)
    pdf_row = await repo.get_by_reference_and_node(reference_material_id, node_id)
    if pdf_row is None:
        raise StudyMaterialReferenceParseMissingException()

    images = await repo.list_images_for_pdf(cast(UUID, pdf_row.llamaparse_pdf_id))
    structured_data = build_parsed_reference_data(
        cast(dict[str, Any], pdf_row.structured_json), images
    )
    return str(pdf_row.formatted_text or ""), structured_data


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
    user_id: UUID,
    *,
    run_id: UUID | None = None,
    execution_token: UUID | None = None,
) -> StudyMaterialGraphState:
    graph = get_study_material_graph()
    config = {
        "configurable": {
            "session": session,
            "user_id": user_id,
            "run_id": str(run_id) if run_id is not None else None,
            "execution_token": (
                str(execution_token) if execution_token is not None else None
            ),
            "pipeline": GenerationPipeline.STUDY_MATERIAL.value,
        }
    }
    result = cast(
        StudyMaterialGraphState,
        await invoke_graph_with_progress(
            graph,
            cast(dict[str, Any], initial_state),
            config,
            pipeline=GenerationPipeline.STUDY_MATERIAL,
            run_id=run_id,
        ),
    )

    _cleanup_temp_reference(result)

    qc_attempt = result.get("qc_attempt") or 0
    if qc_attempt > 0:
        if result.get("qc_failed_permanently"):
            logger.warning(
                "QC permanently failed after %d attempts for node '%s'. "
                "Content accepted with quality issues — QC result attached.",
                qc_attempt,
                result.get("node_title"),
            )
        elif result.get("qc_passed"):
            logger.info(
                "QC passed on attempt %d for node '%s'.",
                qc_attempt,
                result.get("node_title"),
            )

    if result.get("terminal_llm_failure"):
        logger.warning(
            "Study material LLM generation failed (%s) for node '%s' — "
            "persisting placeholder draft with diagnostics.",
            result.get("llm_error_type"),
            result.get("node_title"),
        )
        return result

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
    user_id: UUID | None = None,
    *,
    run_id: UUID | None = None,
    execution_token: UUID | None = None,
) -> StudyMaterialGraphState:
    """First-time generate: resolver → optional llamaparse → study_agent."""
    if user_id is None:
        raise ValueError("user_id is required for study material generation.")

    initial_state: StudyMaterialGraphState = {
        "node_id": node_id,
        "reference_material_id": reference_material_id,
        "generation_mode": "generate",
        "skip_llamaparse": False,
    }
    return await _run_graph(
        session,
        initial_state,
        user_id,
        run_id=run_id,
        execution_token=execution_token,
    )


async def run_study_material_from_checkpoint(
    session: AsyncSession,
    initial_state: StudyMaterialGraphState,
    user_id: UUID,
    *,
    run_id: UUID | None = None,
    execution_token: UUID | None = None,
) -> StudyMaterialGraphState:
    """Resume a failed run from a hydrated checkpoint state."""
    return await _run_graph(
        session,
        initial_state,
        user_id,
        run_id=run_id,
        execution_token=execution_token,
    )


async def run_study_material_regeneration(
    session: AsyncSession,
    node_id: UUID,
    current_draft_content: str,
    mentor_regeneration_goal: str,
    reference_material_id: UUID | None,
    user_id: UUID,
    *,
    hydration: dict[str, Any] | None = None,
    failed_qc_feedback: str | None = None,
    run_id: UUID | None = None,
    execution_token: UUID | None = None,
) -> StudyMaterialGraphState:
    """Regenerate from active draft + mentor feedback. Skips LlamaParse when persisted."""
    extracted_text = ""
    parsed_data: dict = {}
    skip_llamaparse = False

    if reference_material_id is not None:
        extracted_text, parsed_data = await _load_persisted_reference(
            session, reference_material_id, node_id
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
        "failed_qc_feedback": failed_qc_feedback,
    }
    if hydration:
        cast(dict[str, Any], initial_state).update(hydration)
    return await _run_graph(
        session,
        initial_state,
        user_id,
        run_id=run_id,
        execution_token=execution_token,
    )


async def run_study_material_improve(
    session: AsyncSession,
    node_id: UUID,
    current_draft_content: str,
    mentor_feedback: str,
    reference_material_id: UUID | None,
    user_id: UUID,
    *,
    hydration: dict[str, Any] | None = None,
    failed_qc_feedback: str | None = None,
    run_id: UUID | None = None,
    execution_token: UUID | None = None,
) -> StudyMaterialGraphState:
    """Improve active draft surgically. Skips LlamaParse when persisted reference exists."""
    extracted_text = ""
    parsed_data: dict = {}
    skip_llamaparse = False

    if reference_material_id is not None:
        extracted_text, parsed_data = await _load_persisted_reference(
            session, reference_material_id, node_id
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
        "failed_qc_feedback": failed_qc_feedback,
    }
    if hydration:
        cast(dict[str, Any], initial_state).update(hydration)
    return await _run_graph(
        session,
        initial_state,
        user_id,
        run_id=run_id,
        execution_token=execution_token,
    )
