"""Resolve LlamaParse output from DB cache or a fresh LlamaCloud extraction."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.reference_llamaparse_images import (
    ReferenceLlamaParseImage,
)
from src.api.data.models.postgres.e_learning_content.reference_llamaparse_pdf import (
    ReferenceLlamaParsePdf,
)
from src.api.data.repositories import (
    ReferenceLlamaParseRepository,
)
from src.api.schemas.study_material_schemas.llama_parse_schema import (
    LlamaParseExtractionResult,
    ParseImageRecord,
)
from src.api.utils.reference_llamaparse_utils.llama_parse_extractor import (
    compute_pdf_content_hash,
    extract_structured_reference,
    fetch_structured_data_from_extract_job,
)
from src.api.utils.storage.object_storage import exists

logger = logging.getLogger(__name__)


async def _cached_image_files_exist(images: list[ReferenceLlamaParseImage]) -> bool:
    """Return True when every stored figure path is still readable."""
    if not images:
        return True
    checks = await asyncio.gather(*(exists(image.file_url) for image in images))
    return all(checks)


def _images_to_parse_records(
    images: list[ReferenceLlamaParseImage],
) -> list[ParseImageRecord]:
    return [
        ParseImageRecord(
            parse_index=int(image.parse_index or order),
            page_number=int(image.source_page_number or 1),
            figure_index_on_page=int(image.figure_index_on_page or 1),
            filename=image.filename,
            path=image.file_url,
            category=image.category,
        )
        for order, image in enumerate(images)
    ]


def _structured_json_is_complete(structured_json: dict[str, Any] | None) -> bool:
    return bool(structured_json and structured_json.get("sections"))


async def _resolve_structured_json(
    pdf_row: ReferenceLlamaParsePdf,
    api_key: str,
) -> tuple[dict[str, Any], bool]:
    """Return structured JSON from DB, or fetch it from LlamaCloud as a fallback."""
    stored = pdf_row.structured_json
    if _structured_json_is_complete(stored):
        return dict(stored), False

    logger.warning(
        "Cached LlamaParse row %s missing structured JSON; fetching extract job %s",
        pdf_row.llamaparse_pdf_id,
        pdf_row.llama_parse_job_id,
    )
    fetched = await asyncio.to_thread(
        fetch_structured_data_from_extract_job,
        api_key,
        pdf_row.llama_parse_job_id,
    )
    return fetched, True


def _build_extraction_from_cached_row(
    pdf_row: ReferenceLlamaParsePdf,
    images: list[ReferenceLlamaParseImage],
    *,
    content_hash: str,
    structured_data: dict[str, Any],
    skip_persist: bool,
) -> LlamaParseExtractionResult:
    return LlamaParseExtractionResult(
        structured_data=structured_data,
        extract_job_id=pdf_row.llama_parse_job_id,
        parse_job_id=pdf_row.llama_parse_parse_job_id,
        content_hash=content_hash,
        parse_images=_images_to_parse_records(images),
        reused_from_cache=True,
        skip_persist=skip_persist,
    )


async def _try_load_cached_extraction(
    session: AsyncSession,
    *,
    content_hash: str,
    reference_material_id: UUID,
    node_id: UUID,
    api_key: str,
) -> LlamaParseExtractionResult | None:
    """Load a prior parse for identical PDF bytes from the database.

    This implements a two-tier caching strategy:
    1. CONTEXTUAL CHECK: Looks up the cache specifically by reference_material_id
       and node_id. If found and the content_hash matches, we reuse the row. Since the
       context association already exists in the database, we skip database persistence.
    2. CONTENT-ADDRESSABLE FALLBACK: If the current context is new, checks if this
       identical PDF has been parsed anywhere else in the system (by content_hash). If so,
       we reuse the cached JSON and image assets to avoid slow and expensive LlamaParse
       API calls. We set skip_persist=False to save this new node-to-reference link.
    """
    repo = ReferenceLlamaParseRepository(session)

    # --- TIER 1: Check if this specific node + reference material combination has this file cached ---
    current = await repo.get_by_reference_and_node(reference_material_id, node_id)
    if current is not None and current.content_hash == content_hash:
        images = await repo.list_images_for_pdf(current.llamaparse_pdf_id)
        if await _cached_image_files_exist(images):
            try:
                structured_data, json_fetched = await _resolve_structured_json(
                    current, api_key
                )
            except Exception:
                logger.exception(
                    "Failed to load structured JSON for cached material=%s node=%s",
                    reference_material_id,
                    node_id,
                )
                return None

            logger.info(
                "Reusing existing LlamaParse row for material=%s node=%s (hash=%s)",
                reference_material_id,
                node_id,
                content_hash[:12],
            )
            return _build_extraction_from_cached_row(
                current,
                images,
                content_hash=content_hash,
                structured_data=structured_data,
                # If json wasn't fetched from LlamaCloud, it is already in our DB for this node,
                # so we skip persisting it again.
                skip_persist=not json_fetched,
            )

    # --- TIER 2: Fallback to checking if the same file bytes (content_hash) were parsed anywhere else ---
    cached = await repo.get_with_images_by_content_hash(content_hash)
    if cached is None:
        return None

    pdf_row, images = cached
    if not await _cached_image_files_exist(images):
        logger.warning(
            "Cached LlamaParse images missing on disk for hash=%s; will re-extract",
            content_hash[:12],
        )
        return None

    try:
        structured_data, _json_fetched = await _resolve_structured_json(
            pdf_row, api_key
        )
    except Exception:
        logger.exception(
            "Failed to load structured JSON for hash reuse job=%s",
            pdf_row.llama_parse_job_id,
        )
        return None

    logger.info(
        "Reusing LlamaParse result from job %s for identical PDF hash=%s",
        pdf_row.llama_parse_job_id,
        content_hash[:12],
    )
    return _build_extraction_from_cached_row(
        pdf_row,
        images,
        content_hash=content_hash,
        structured_data=structured_data,
        # Set skip_persist=False so the caller writes a new database link associating
        # this new (reference_material_id, node_id) context with the existing parse row.
        skip_persist=False,
    )


async def resolve_reference_extraction(
    session: AsyncSession,
    *,
    file_path: str,
    api_key: str,
    reference_material_id: UUID,
    node_id: UUID,
    topic_title: str = "topic",
    material_label: str | None = None,
) -> LlamaParseExtractionResult:
    """Return cached parse output for identical PDF bytes or run a new extraction."""
    content_hash = compute_pdf_content_hash(file_path)

    cached = await _try_load_cached_extraction(
        session,
        content_hash=content_hash,
        reference_material_id=reference_material_id,
        node_id=node_id,
        api_key=api_key,
    )
    if cached is not None:
        return cached

    extraction = await asyncio.to_thread(
        extract_structured_reference,
        file_path,
        api_key,
        node_id=node_id,
        topic_title=topic_title,
        reference_material_id=reference_material_id,
        material_label=material_label,
    )

    if extraction.content_hash != content_hash:
        extraction.content_hash = content_hash

    return extraction
