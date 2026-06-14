"""Extract structured content from an attached reference PDF via LlamaParse."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.api.config.dbconfig import settings
from src.api.core.agents.study_material.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.llama_parse_extractor import (
    extract_structured_reference,
)
from src.api.utils.study_agent_utils.reference_cache import save_reference_cache
from src.api.utils.study_agent_utils.reference_formatter import (
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

    api_key = settings.llama_parse_api_key
    if not api_key:
        return {"error": "LLAMA_PARSE_API_KEY is not configured."}

    topic_title = state.get("node_title") or "topic"
    material_id = state.get("reference_material_id")
    material_label = state.get("reference_material_title") or Path(file_path).stem

    try:
        structured_data = await asyncio.to_thread(
            extract_structured_reference,
            file_path,
            api_key,
            topic_title=topic_title,
            reference_material_id=material_id,
            material_label=material_label,
        )
    except Exception as exc:
        logger.exception("LlamaParse extraction failed")
        return {"error": f"LlamaParse extraction failed: {exc}"}

    try:
        reference_text = format_parsed_reference(structured_data)
    except Exception as exc:
        logger.exception("Reference formatting failed after LlamaParse extraction")
        return {"error": f"Reference formatting failed: {exc}"}

    reference_material_id = state.get("reference_material_id")
    if reference_material_id is not None:
        try:
            save_reference_cache(
                file_path,
                reference_material_id,
                reference_text,
                structured_data,
            )
        except OSError as exc:
            logger.warning("Could not save reference cache: %s", exc)

    return {
        "parsed_reference_data": structured_data,
        "extracted_reference_text": reference_text,
    }
