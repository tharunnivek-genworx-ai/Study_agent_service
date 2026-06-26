"""Concept checklist and topic_split shapes parsed from the checklist LLM."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

ConceptDomain = Literal["STEM", "Programming", "Conceptual", "Mixed", ""]
MustCoverPriority = Literal["required", "recommended"]

_VALID_DOMAINS = frozenset({"STEM", "Programming", "Conceptual", "Mixed"})


def _checklist_section_id(item: dict[str, Any]) -> str:
    """Document section id for a must_cover item (topic_split id or legacy mc id)."""
    section_id = str(item.get("section_id", "")).strip()
    if section_id:
        return section_id
    return str(item.get("id", "")).strip()


class TopicSplitEntry(BaseModel):
    id: str
    heading: str
    purpose: str = ""


class MustCoverItem(BaseModel):
    id: str
    concept: str
    requirement: str
    priority: MustCoverPriority = "recommended"
    section_id: str | None = None
    depth_gate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ConceptPlanOut(BaseModel):
    """Parsed concept checklist LLM output: domain, blueprint, and must-cover items."""

    domain: str = ""
    topic_split: list[TopicSplitEntry] = Field(default_factory=list)
    must_cover_checklist: list[MustCoverItem] = Field(default_factory=list)

    @property
    def topic_split_dicts(self) -> list[dict[str, Any]]:
        return [entry.model_dump(exclude_none=True) for entry in self.topic_split]

    @property
    def must_cover_checklist_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.must_cover_checklist]


def _extract_checklist_json_payload(text: str) -> Any:
    """Parse concept-checklist LLM output (object or legacy array)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, cleaned, re.DOTALL)
        if not match:
            continue
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return None


def _validate_topic_split_entry(
    item: dict[str, Any],
    index: int,
) -> TopicSplitEntry | None:
    entry_id = str(item.get("id") or f"ts_{index}").strip()
    heading = str(
        item.get("heading") or item.get("concept") or f"Section {index}"
    ).strip()
    if not entry_id or not heading:
        return None
    return TopicSplitEntry(
        id=entry_id,
        heading=heading,
        purpose=str(item.get("purpose") or item.get("requirement") or "").strip(),
    )


def _validate_checklist_entry(
    item: dict[str, Any],
    index: int,
) -> MustCoverItem | None:
    concept = item.get("concept") or item.get("name") or f"item_{index}"
    requirement = item.get("requirement") or item.get("description") or str(item)
    priority = item.get("priority", "recommended")
    if priority not in ("required", "recommended"):
        priority = "recommended"
    section_id = str(item.get("section_id", "")).strip() or None
    depth_gate = str(item.get("depth_gate", "")).strip() or None
    return MustCoverItem(
        id=str(item.get("id") or f"mc_{index}").strip(),
        concept=str(concept),
        requirement=str(requirement),
        priority=priority,
        section_id=section_id,
        depth_gate=depth_gate,
    )


def derive_topic_split_from_checklist(
    checklist: list[dict[str, Any]] | list[MustCoverItem],
) -> list[TopicSplitEntry]:
    """Build a minimal topic_split when the LLM returns only a checklist array."""
    seen: dict[str, TopicSplitEntry] = {}
    for index, item in enumerate(checklist, start=1):
        if isinstance(item, MustCoverItem):
            item_dict = item.to_dict()
        else:
            item_dict = cast(dict[str, Any], item)
        section_id = _checklist_section_id(item_dict)
        if not section_id or section_id in seen:
            continue
        seen[section_id] = TopicSplitEntry(
            id=section_id,
            heading=str(item_dict.get("concept") or f"Section {index}"),
            purpose=str(item_dict.get("requirement") or ""),
        )
    return list(seen.values())


def _normalize_domain(raw: Any) -> str:
    domain = str(raw or "").strip()
    if domain in _VALID_DOMAINS:
        return domain
    return ""


def parse_concept_checklist_response(raw: str) -> ConceptPlanOut | None:
    """Parse topic_split + must_cover_checklist from concept-checklist LLM output."""
    parsed = _extract_checklist_json_payload(raw)
    if parsed is None:
        return None

    if isinstance(parsed, list):
        checklist = [
            entry
            for index, item in enumerate(parsed, start=1)
            if isinstance(item, dict)
            for entry in [_validate_checklist_entry(item, index)]
            if entry is not None
        ]
        if not checklist:
            return None
        return ConceptPlanOut(
            domain="",
            topic_split=derive_topic_split_from_checklist(checklist),
            must_cover_checklist=checklist,
        )

    if not isinstance(parsed, dict):
        return None

    raw_checklist = parsed.get("must_cover_checklist") or []
    if not isinstance(raw_checklist, list):
        return None

    checklist = [
        entry
        for index, item in enumerate(raw_checklist, start=1)
        if isinstance(item, dict)
        for entry in [_validate_checklist_entry(item, index)]
        if entry is not None
    ]
    if not checklist:
        return None

    raw_split = parsed.get("topic_split") or []
    topic_split: list[TopicSplitEntry] = []
    if isinstance(raw_split, list):
        topic_split = [
            entry
            for index, item in enumerate(raw_split, start=1)
            if isinstance(item, dict)
            for entry in [_validate_topic_split_entry(item, index)]
            if entry is not None
        ]
    if not topic_split:
        topic_split = derive_topic_split_from_checklist(checklist)

    return ConceptPlanOut(
        domain=_normalize_domain(parsed.get("domain")),
        topic_split=topic_split,
        must_cover_checklist=checklist,
    )


def fallback_checklist(teaching_instruction: str) -> list[dict[str, Any]]:
    """Derive a minimal checklist by splitting the instruction into sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", teaching_instruction.strip())
    items: list[dict[str, Any]] = []
    for i, sentence in enumerate(sentences, start=1):
        cleaned = sentence.strip(" .-")
        if len(cleaned) < 10:
            continue
        items.append(
            {
                "id": f"mc_{i}",
                "concept": f"Instruction item {i}",
                "requirement": cleaned,
                "priority": "recommended",
                "section_id": f"ts_{i}",
            }
        )
    if not items:
        items.append(
            {
                "id": "mc_1",
                "concept": "Core topic coverage",
                "requirement": "Provide a complete, accurate explanation of the topic.",
                "priority": "required",
                "section_id": "ts_1",
            }
        )
    return items


def fallback_topic_split(checklist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive topic_split entries when checklist generation falls back."""
    return [
        entry.model_dump(exclude_none=True)
        for entry in derive_topic_split_from_checklist(checklist)
    ]


def parse_checklist(raw: str) -> list[dict[str, Any]] | None:
    """Extract must_cover_checklist from concept-checklist LLM output."""
    parsed = parse_concept_checklist_response(raw)
    if parsed is None:
        return None
    return parsed.must_cover_checklist_dicts
