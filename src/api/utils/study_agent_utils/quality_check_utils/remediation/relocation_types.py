"""Datatypes for deterministic block-placement remediation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RelocationAction = Literal["extract", "dereference", "move_block", "fill_explanation"]
RelocationConfidence = Literal["high", "low"]
BlockKind = Literal["code_blocks", "formula_blocks"]


@dataclass
class Relocation:
    action: RelocationAction
    confidence: RelocationConfidence
    section_id: str
    subsection_heading: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    span_text: str | None = None
    replacement: str | None = None
    block_kind: BlockKind | None = None
    block_index: int | None = None
    target_kind: BlockKind | None = None
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "confidence": self.confidence,
            "section_id": self.section_id,
        }
        if self.subsection_heading is not None:
            payload["subsection_heading"] = self.subsection_heading
        if self.span_start is not None:
            payload["span_start"] = self.span_start
        if self.span_end is not None:
            payload["span_end"] = self.span_end
        if self.span_text is not None:
            payload["span_text"] = self.span_text
        if self.replacement is not None:
            payload["replacement"] = self.replacement
        if self.block_kind is not None:
            payload["block_kind"] = self.block_kind
        if self.block_index is not None:
            payload["block_index"] = self.block_index
        if self.target_kind is not None:
            payload["target_kind"] = self.target_kind
        if self.explanation is not None:
            payload["explanation"] = self.explanation
        return payload


@dataclass
class RelocationPlan:
    check_id: str
    section_id: str
    relocations: list[Relocation] = field(default_factory=list)

    @property
    def has_low_confidence(self) -> bool:
        return any(r.confidence == "low" for r in self.relocations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "section_id": self.section_id,
            "relocations": [r.to_dict() for r in self.relocations],
            "has_low_confidence": self.has_low_confidence,
        }


@dataclass
class RemediationReport:
    fixed_section_ids: list[str]
    all_resolved: bool
    needs_llm_fallback: bool
    applied_plans: list[RelocationPlan] = field(default_factory=list)
    skipped_low_confidence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed_section_ids": self.fixed_section_ids,
            "all_resolved": self.all_resolved,
            "needs_llm_fallback": self.needs_llm_fallback,
            "skipped_low_confidence": self.skipped_low_confidence,
            "applied_plans": [p.to_dict() for p in self.applied_plans],
        }
