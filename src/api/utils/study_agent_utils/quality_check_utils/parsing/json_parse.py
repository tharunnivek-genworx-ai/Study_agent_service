# src/api/utils/study_agent_utils/qc/json_parse.py
"""Robust JSON object parsing for LLM QC responses."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from src.api.schemas.qc_schemas import is_valid_qc_verification_response

logger = logging.getLogger(__name__)

_MAX_TRAILING_BRACE_TRIMS = 5


def _strip_outer_fence(text: str) -> str:
    """Strip a single outer markdown fence when the response starts with one."""
    if not text.startswith("```"):
        return text
    fence_end = text.rfind("```")
    if fence_end <= 2:
        return text
    inner = text[3:fence_end]
    newline = inner.find("\n")
    if newline != -1:
        inner = inner[newline + 1 :]
    return inner.strip()


def _find_json_start(text: str) -> int:
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            return i
    return -1


def _try_raw_decode(text: str) -> dict[str, Any] | None:
    """Parse the first JSON object via raw_decode (ignores trailing junk)."""
    start = _find_json_start(text)
    if start == -1:
        return None
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return cast(dict[str, Any], obj)
    return None


def _try_trim_trailing_braces(text: str) -> dict[str, Any] | None:
    """Repair responses with extra closing braces before json.loads."""
    start = _find_json_start(text)
    if start == -1:
        return None
    candidate = text[start:].strip()
    for _ in range(_MAX_TRAILING_BRACE_TRIMS):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            if not candidate.rstrip().endswith("}"):
                break
            candidate = candidate.rstrip()[:-1].rstrip()
            continue
        if isinstance(obj, dict):
            return cast(dict[str, Any], obj)
        break
    return None


def parse_llm_json_object(raw: str, label: str = "LLM") -> dict[str, Any] | None:
    """Parse a JSON object from an LLM response.

    Tolerates markdown fences, leading preamble, trailing commentary, and
    common malformed closings (e.g. an extra ``}`` after the root object).
    """
    text = _strip_outer_fence(raw.strip())
    if not text:
        return None

    if not text.startswith(("{", "[")):
        idx = _find_json_start(text)
        if idx == -1:
            logger.warning("%s response contained no JSON object: %.200s", label, text)
            return None
        text = text[idx:]

    for parser in (_try_raw_decode, _try_trim_trailing_braces):
        parsed = parser(text)
        if parsed is not None:
            return parsed

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return cast(dict[str, Any], obj)
    except json.JSONDecodeError as exc:
        logger.warning(
            "%s response was not valid JSON (%s): %.200s",
            label,
            exc.msg,
            text,
        )
    return None


def parse_qc_verification_response(
    raw: str, label: str = "LLM"
) -> dict[str, Any] | None:
    """Parse and validate a QC verification response."""
    parsed = parse_llm_json_object(raw, label)
    if parsed is None:
        return None
    if not is_valid_qc_verification_response(parsed):
        logger.warning(
            "%s response JSON is not a valid QC verification object (keys=%s)",
            label,
            sorted(parsed.keys()),
        )
        return None
    return parsed
