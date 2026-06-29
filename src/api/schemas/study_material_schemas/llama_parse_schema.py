"""LlamaParse extraction pipeline shapes (figures and structured job output)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_LLAMA_PARSE_JSON_PATH = Path(__file__).with_name("llama_parse_schema.json")


def load_study_material_schema() -> dict[str, Any]:
    """Load the LlamaCloud extract job JSON schema shipped with this package."""
    data = json.loads(_LLAMA_PARSE_JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Schema JSON is not a dictionary")
    return data


class ParseImageRecord(BaseModel):
    """A downloaded figure from the LlamaParse Parse job."""

    parse_index: int
    page_number: int
    figure_index_on_page: int
    filename: str
    path: str
    category: str | None = None
    bbox_y: float = 0.0


class LlamaParseExtractionResult(BaseModel):
    """Structured output from a single LlamaParse extraction run."""

    structured_data: dict[str, Any]
    extract_job_id: str
    parse_job_id: str | None
    content_hash: str
    parse_images: list[ParseImageRecord] = Field(default_factory=list)
    reused_from_cache: bool = False
    skip_persist: bool = False
