"""Persist LlamaParse extraction output to reference_llamaparse_* tables."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.reference_llamaparse_images import (
    ReferenceLlamaParseImage,
)
from src.api.data.repositories.study_agent_repositories.reference_llamaparse_repository import (
    ReferenceLlamaParseRepository,
)
from src.api.utils.reference_llamaparse_utils.llama_parse_extractor import (
    LlamaParseExtractionResult,
    ParseImageRecord,
)

logger = logging.getLogger(__name__)


def _build_image_title_lookup(
    structured_data: dict[str, Any],
) -> dict[tuple[int, int], str]:
    """Map (page_number, ordinal_on_page) → human-readable title from section metadata."""
    lookup: dict[tuple[int, int], str] = {}
    ordinal_by_page: dict[int, int] = {}

    for section in structured_data.get("sections") or []:
        for image in section.get("images") or []:
            page = image.get("source_page") or image.get("page_number")
            if page is None:
                continue
            page_num = int(page)
            ordinal_by_page[page_num] = ordinal_by_page.get(page_num, 0) + 1
            ordinal = ordinal_by_page[page_num]
            label = (
                image.get("figure_label")
                or image.get("semantic_name")
                or section.get("heading")
                or f"Figure on page {page_num}"
            )
            lookup[(page_num, ordinal)] = str(label).strip()

    return lookup


def _title_for_reference_image(
    image_record: ParseImageRecord,
    title_lookup: dict[tuple[int, int], str],
) -> str:
    page = image_record.page_number
    figure_index = image_record.figure_index_on_page
    if (page, figure_index) in title_lookup:
        return title_lookup[(page, figure_index)]

    if image_record.filename:
        return image_record.filename
    return f"Reference figure (page {page})"


def build_parsed_reference_data_from_extraction(
    extraction: LlamaParseExtractionResult,
) -> dict[str, Any]:
    """Build graph state payload immediately after an extraction run."""
    data = dict(extraction.structured_data)
    data["reference_images"] = [
        {
            "filename": image.filename,
            "storage_path": image.path,
            "source_page": image.page_number,
            "figure_index_on_page": image.figure_index_on_page,
            "parse_index": image.parse_index,
            "category": image.category,
        }
        for image in extraction.parse_images
    ]
    return data


def build_parsed_reference_data(
    structured_json: dict[str, Any],
    images: list[ReferenceLlamaParseImage],
) -> dict[str, Any]:
    """Rebuild graph state payload from persisted parse rows."""
    data = dict(structured_json)
    data["reference_images"] = [
        {
            "filename": image.filename,
            "storage_path": image.file_url,
            "source_page": image.source_page_number,
            "figure_index_on_page": image.figure_index_on_page,
            "parse_index": image.parse_index,
            "category": image.category,
            "title": image.title,
        }
        for image in images
    ]
    return data


async def persist_reference_llamaparse(
    session: AsyncSession,
    *,
    reference_material_id: UUID,
    node_id: UUID,
    space_id: UUID,
    parsed_by: UUID,
    extraction: LlamaParseExtractionResult,
    formatted_text: str,
) -> None:
    """Upsert parse JSON and extracted figure rows for a reference material + node."""
    title_lookup = _build_image_title_lookup(extraction.structured_data)
    image_payloads: list[dict[str, Any]] = []

    for order_index, image_record in enumerate(extraction.parse_images):
        image_payloads.append(
            {
                "title": _title_for_reference_image(image_record, title_lookup),
                "filename": image_record.filename,
                "file_url": image_record.path,
                "source_page_number": image_record.page_number,
                "figure_index_on_page": image_record.figure_index_on_page,
                "parse_index": image_record.parse_index,
                "category": image_record.category,
                "order_index": order_index,
            }
        )

    repo = ReferenceLlamaParseRepository(session)
    await repo.upsert_parse_result(
        reference_material_id=reference_material_id,
        node_id=node_id,
        space_id=space_id,
        llama_parse_job_id=extraction.extract_job_id,
        llama_parse_parse_job_id=extraction.parse_job_id,
        content_hash=extraction.content_hash,
        structured_json=extraction.structured_data,
        formatted_text=formatted_text,
        parsed_by=parsed_by,
        images=image_payloads,
    )

    if image_payloads:
        logger.info(
            "Persisted %d reference_llamaparse image(s) for node %s",
            len(image_payloads),
            node_id,
        )
