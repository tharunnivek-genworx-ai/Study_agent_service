"""Disk cache for LlamaParse output — avoids re-parsing on regenerate/improve."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def reference_cache_path(pdf_path: str | Path) -> Path:
    """Canonical cache file adjacent to the source PDF."""
    source = Path(pdf_path)
    return source.parent / f"{source.stem}_reference_cache.json"


def save_reference_cache(
    pdf_path: str | Path,
    reference_material_id: UUID,
    formatted_text: str,
    structured_data: dict[str, Any],
) -> Path:
    """Persist formatted reference text and structured data for later reuse."""
    cache_path = reference_cache_path(pdf_path)
    payload = {
        "reference_material_id": str(reference_material_id),
        "formatted_text": formatted_text,
        "structured_data": structured_data,
        "cached_at": datetime.now(UTC).isoformat(),
    }
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Reference cache saved → %s", cache_path)
    return cache_path


def load_reference_cache(
    pdf_path: str | Path,
    reference_material_id: UUID | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Load cached reference text. Returns None if cache is missing or stale."""
    cache_path = reference_cache_path(pdf_path)
    if not cache_path.is_file():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read reference cache %s: %s", cache_path, exc)
        return None

    if reference_material_id is not None:
        cached_id = payload.get("reference_material_id")
        if cached_id and str(reference_material_id) != cached_id:
            logger.warning("Reference cache material_id mismatch for %s", cache_path)
            return None

    formatted_text = payload.get("formatted_text") or ""
    structured_data = payload.get("structured_data") or {}
    if not formatted_text.strip() and not structured_data:
        return None

    return formatted_text, structured_data
