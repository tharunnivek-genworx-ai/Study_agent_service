"""JSON parse helpers for external-research LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str | None) -> dict[str, Any] | None:
    """Parse a JSON object from model output (fences / preamble tolerant)."""
    if not text or not text.strip():
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None
