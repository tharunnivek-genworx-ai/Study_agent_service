"""Conditional paragraph-boundary chunking (design §8).

Normalizes newlines, packs segments to a token target, and hard-splits any
oversized segment so a single block never remains above the threshold.
``was_chunked`` is true only when more than one chunk is produced.
"""

from __future__ import annotations

import re
from typing import Any

from src.api.config import external_research_settings
from src.api.utils.external_research_utils.tokens import rough_token_count

_BLANK_LINE_RUN = re.compile(r"\n[ \t]*\n+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _normalize_newlines(text: str) -> str:
    """Collapse CRLF/CR to LF and blank-line runs to paragraph breaks."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BLANK_LINE_RUN.sub("\n\n", normalized)
    return normalized.strip()


def _line_groups(block: str, target_tokens: int) -> list[str]:
    """Split a single block on ``\\n`` into line-groups.

    Consecutive non-empty lines stay together while the group remains under
    ``target_tokens``. Empty lines flush the current group.
    """
    lines = block.split("\n")
    groups: list[str] = []
    current: list[str] = []

    for line in lines:
        if not line.strip():
            if current:
                groups.append("\n".join(current))
                current = []
            continue

        prospective = "\n".join(current + [line]) if current else line
        if current and rough_token_count(prospective) > target_tokens:
            groups.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        groups.append("\n".join(current))

    return groups if groups else [block]


def _segments_from_text(text: str, target_tokens: int) -> list[str]:
    """Normalize and segment text into packable units."""
    normalized = _normalize_newlines(text)
    if not normalized:
        return [text] if text else [""]

    paragraphs = [p for p in normalized.split("\n\n") if p.strip()]
    if not paragraphs:
        return [normalized]

    # Wave-like pages often use only single newlines — fall back to line-groups.
    if len(paragraphs) == 1 and "\n" in paragraphs[0]:
        return _line_groups(paragraphs[0], target_tokens)

    return paragraphs


def _hard_split_by_words(segment: str, target_tokens: int) -> list[str]:
    words = segment.split()
    if not words:
        return [segment]
    if len(words) == 1:
        # Single token longer than threshold — cannot split further.
        return [segment]

    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        # Count the prospective joined string — summing per-word estimates
        # undercounts because rough_token_count uses int(words * 1.3).
        prospective = " ".join(current + [word]) if current else word
        if current and rough_token_count(prospective) > target_tokens:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _hard_split_segment(segment: str, target_tokens: int) -> list[str]:
    """Split one oversized segment by sentences, then by words if needed."""
    if rough_token_count(segment) <= target_tokens:
        return [segment]

    sentences = [s for s in _SENTENCE_BOUNDARY.split(segment) if s.strip()]
    if len(sentences) <= 1:
        return _hard_split_by_words(segment, target_tokens)

    packed = _pack_units(sentences, target_tokens, joiner=" ")
    result: list[str] = []
    for piece in packed:
        if rough_token_count(piece) > target_tokens:
            result.extend(_hard_split_by_words(piece, target_tokens))
        else:
            result.append(piece)
    return result


def _pack_units(
    units: list[str],
    target_tokens: int,
    *,
    joiner: str,
) -> list[str]:
    """Pack units until ``target_tokens``, hard-splitting any oversized unit."""
    chunks: list[str] = []
    current: list[str] = []

    for unit in units:
        unit_tokens = rough_token_count(unit)
        if unit_tokens > target_tokens:
            if current:
                chunks.append(joiner.join(current))
                current = []
            chunks.extend(_hard_split_segment(unit, target_tokens))
            continue

        prospective = joiner.join(current + [unit]) if current else unit
        if current and rough_token_count(prospective) > target_tokens:
            chunks.append(joiner.join(current))
            current = [unit]
        else:
            current.append(unit)

    if current:
        chunks.append(joiner.join(current))

    return chunks if chunks else list(units)


def split_into_chunks(text: str, target_tokens: int) -> list[str]:
    """Chunk text at paragraph/line boundaries with hard-split fallback.

    Never leaves a multi-word chunk whose rough token count exceeds
    ``target_tokens``.
    """
    if not text or not text.strip():
        return [text]

    if target_tokens <= 0:
        return [text]

    segments = _segments_from_text(text, target_tokens)
    packed = _pack_units(segments, target_tokens, joiner="\n\n")

    result: list[str] = []
    for chunk in packed:
        if rough_token_count(chunk) > target_tokens:
            result.extend(_hard_split_segment(chunk, target_tokens))
        else:
            result.append(chunk)

    return result if result else [text]


def chunk_cleaned_pages(
    cleaned_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    threshold = external_research_settings.external_research_chunk_token_threshold
    chunked_pages: list[dict[str, Any]] = []
    for page in cleaned_pages:
        text = str(page.get("cleaned_text") or "")
        token_count = rough_token_count(text)
        if token_count <= threshold:
            chunks = [text]
        else:
            chunks = split_into_chunks(text, target_tokens=threshold)

        chunked_pages.append(
            {
                "url": page.get("url"),
                "chunks": chunks,
                # True only when the page actually produced multiple chunks —
                # not merely because token_count exceeded the threshold.
                "was_chunked": len(chunks) > 1,
            }
        )
    return chunked_pages
