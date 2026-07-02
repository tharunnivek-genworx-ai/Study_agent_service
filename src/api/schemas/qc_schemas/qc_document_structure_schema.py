"""QC document extraction shapes derived from study material JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CodeArtifact(BaseModel):
    """One code block extracted from a study document for deterministic QC."""

    id: str
    language: str
    body: str
    fenced_code: str
    line_count: int
    section_id: str | None = None
    section_heading: str | None = None
    subsection_heading: str | None = None


class DocumentStructure(BaseModel):
    """Flattened section list and code artifacts parsed from a study document."""

    sections: list[dict[str, Any]] = Field(default_factory=list)
    code_artifacts: list[CodeArtifact] = Field(default_factory=list)
    has_preamble: bool = False
