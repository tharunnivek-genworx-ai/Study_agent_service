# src/api/control/study_agent/nodes/llamaparse_node.py

"""Extract structured content from an attached reference PDF via LlamaParse."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.data.repositories import (
    NodeRepository,
)
from src.api.utils.reference_llamaparse_utils.reference_llamaparse_cache import (
    resolve_reference_extraction,
)
from src.api.utils.reference_llamaparse_utils.reference_llamaparse_persistence import (
    build_parsed_reference_data_from_extraction,
    persist_reference_llamaparse,
)
from src.api.utils.reference_media_utils.reference_formatter import (
    format_parsed_reference,
)

logger = logging.getLogger(__name__)


async def llamaparse_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    file_path = state.get("reference_file_path")
    if not file_path:
        return {"extracted_reference_text": "", "parsed_reference_data": {}}

    api_key = llm_settings.llama_parse_api_key
    if not api_key:
        return {"error": "LLAMA_PARSE_API_KEY is not configured."}

    node_id = state.get("node_id")
    reference_material_id = state.get("reference_material_id")
    if node_id is None or reference_material_id is None:
        return {
            "error": "node_id and reference_material_id are required for LlamaParse."
        }

    configurable = config.get("configurable") or {}
    session = configurable.get("session")
    user_id = configurable.get("user_id")
    if session is None or user_id is None:
        return {"error": "Database session and user_id are required for LlamaParse."}

    topic_title = state.get("node_title") or "topic"
    material_label = state.get("reference_material_title") or Path(file_path).stem

    try:
        extraction = await resolve_reference_extraction(
            session,
            file_path=file_path,
            api_key=api_key,
            reference_material_id=reference_material_id,
            node_id=node_id,
            topic_title=topic_title,
            material_label=material_label,
        )
    except Exception as exc:
        logger.exception("LlamaParse extraction failed")
        return {"error": f"LlamaParse extraction failed: {exc}"}

    if extraction.reused_from_cache:
        logger.info(
            "LlamaParse cache hit for node %s (extract_job=%s)",
            node_id,
            extraction.extract_job_id,
        )

    try:
        reference_text = format_parsed_reference(extraction.structured_data)
    except Exception as exc:
        logger.exception("Reference formatting failed after LlamaParse extraction")
        return {"error": f"Reference formatting failed: {exc}"}

    if not extraction.skip_persist:
        node_repo = NodeRepository(session)
        node = await node_repo.get_node_by_id(node_id)
        if node is None:
            return {"error": f"Node not found: {node_id}"}

        try:
            await persist_reference_llamaparse(
                session,
                reference_material_id=reference_material_id,
                node_id=node_id,
                space_id=cast(UUID, node.space_id),
                parsed_by=UUID(str(user_id)),
                extraction=extraction,
                formatted_text=reference_text,
            )
        except Exception as exc:
            logger.exception("Failed to persist LlamaParse output")
            return {"error": f"Failed to persist LlamaParse output: {exc}"}

    return {
        "parsed_reference_data": build_parsed_reference_data_from_extraction(
            extraction
        ),
        "extracted_reference_text": reference_text,
    }
