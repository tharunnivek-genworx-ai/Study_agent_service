"""Prepare JSON study documents before QC LLM calls."""

from __future__ import annotations

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
)


def prepare_document_for_qc(
    content: str,
    *,
    max_chars: int,
    aggressive: bool = False,
) -> tuple[str, bool]:
    """Return one clean JSON object string for Nemotron (no fences or commentary)."""
    prepared = canonicalize_generation_json(content)
    limit = max_chars // 2 if aggressive else max_chars
    if len(prepared) <= limit:
        return prepared, False
    return prepared[:limit], True
