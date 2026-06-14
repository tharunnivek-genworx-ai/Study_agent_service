"""Persist LlamaParse reference figures into node_media rows."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories.study_agent_repositories.reference_material_repository import (
    ReferenceMaterialRepository,
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
    image_record: dict[str, Any],
    title_lookup: dict[tuple[int, int], str],
) -> str:
    page = int(image_record.get("source_page") or 1)
    figure_index = int(image_record.get("figure_index_on_page") or 1)
    if (page, figure_index) in title_lookup:
        return title_lookup[(page, figure_index)]

    filename = image_record.get("filename") or ""
    if filename:
        return filename
    return f"Reference figure (page {page})"


async def replace_pdf_extracted_node_media(
    session: AsyncSession,
    *,
    node_id: UUID,
    reference_material_id: UUID,
) -> int:
    """Remove prior PDF-extracted images for this node + reference material."""
    repo = ReferenceMaterialRepository(session)
    removed = await repo.delete_pdf_extracted_media(node_id, reference_material_id)
    if removed:
        logger.info(
            "Removed %d prior PDF-extracted node_media row(s) for node %s",
            removed,
            node_id,
        )
    return removed


async def persist_reference_images_to_node_media(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    reference_material_id: UUID,
    structured_data: dict[str, Any],
    uploaded_by: UUID,
    replace_existing: bool = True,
) -> int:
    """Insert node_media rows for LlamaParse figures not already recorded.

    When replace_existing is True, deletes prior PDF-extracted images for this
    node + reference material before inserting the new batch.

    Returns the number of newly created rows.
    """
    reference_images = structured_data.get("reference_images") or []
    if not reference_images:
        return 0

    repo = ReferenceMaterialRepository(session)

    if replace_existing:
        await replace_pdf_extracted_node_media(
            session,
            node_id=node_id,
            reference_material_id=reference_material_id,
        )

    title_lookup = _build_image_title_lookup(structured_data)
    created = 0

    for order_offset, image_record in enumerate(reference_images):
        storage_path = image_record.get("storage_path")
        if not storage_path:
            continue

        path = Path(storage_path)
        if not path.is_file():
            logger.warning(
                "Skipping node_media insert — image file missing: %s",
                storage_path,
            )
            continue

        source_page = image_record.get("source_page")
        source_page_int = int(source_page) if source_page is not None else None
        title = _title_for_reference_image(image_record, title_lookup)

        await repo.create_media(
            node_id=node_id,
            space_id=space_id,
            media_type="image",
            title=title,
            url=None,
            file_url=storage_path,
            order_index=order_offset,
            uploaded_by=uploaded_by,
            source_pdf_material_id=reference_material_id,
            source_page_number=source_page_int,
        )
        created += 1

    if created:
        logger.info(
            "Persisted %d reference image(s) to node_media for node %s",
            created,
            node_id,
        )

    return created
