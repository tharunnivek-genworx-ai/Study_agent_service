"""Study material generator JSON document shapes (sections, code, formulas)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ReferenceRequiredStatus = Literal["reference_required"]
ImproveStatus = Literal["vague", "generated"]
RegenerateStatus = Literal["vague", "generated"]


class CodeBlock(BaseModel):
    language: str = ""
    code: str = ""
    explanation: str = ""


class FormulaBlock(BaseModel):
    notation: str = ""
    formula: str = ""
    explanation: str = ""


class Subsection(BaseModel):
    heading: str = ""
    content: str = ""
    code_blocks: list[CodeBlock] = Field(default_factory=list)
    formula_blocks: list[FormulaBlock] = Field(default_factory=list)


class Section(BaseModel):
    id: str | None = None
    heading: str = ""
    content: str = ""
    code_blocks: list[CodeBlock] = Field(default_factory=list)
    formula_blocks: list[FormulaBlock] = Field(default_factory=list)
    subsections: list[Subsection] = Field(default_factory=list)


class GenerationDocument(BaseModel):
    """Full study material JSON emitted by the generator (or status-only variants)."""

    sections: list[Section] | None = None
    generation_status: str | None = None
    topic_received: str | None = None
    reason: str | None = None
    message: str | None = None
    improve_status: str | None = None
    regenerate_status: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenerationDocument:
        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def is_status_only(self) -> bool:
        status = str(self.generation_status or "").strip()
        if status == "reference_required":
            return True
        if str(self.improve_status or "").strip() == "vague":
            return True
        if str(self.regenerate_status or "").strip() == "vague":
            return True
        return False

    def has_sections(self) -> bool:
        return isinstance(self.sections, list)
