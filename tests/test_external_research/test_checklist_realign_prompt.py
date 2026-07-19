"""Unit tests for checklist realign prompt builders and truncation."""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.concept.checklist_realign_prompt import (
    DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK,
    build_checklist_realign_system_prompt,
    build_checklist_realign_user_message,
    truncate_research_notes,
)
from src.api.control.study_agent.prompts.concept.shared_blocks import (
    JSON_OUTPUT_SCHEMA,
)


def test_realign_system_prompt_routes_stem_only() -> None:
    system = build_checklist_realign_system_prompt(domain="STEM")
    lower = system.lower()
    assert DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK in system
    assert "never reclassify" in lower
    assert "domain policy — stem" in lower
    assert "stem application" in lower
    assert "concept-scoped note binding (stem)" in lower
    assert "self-check before output (stem)" in lower
    assert "stem hard ban" in lower or "zero code" in lower
    assert "never choose programming implementation" in lower
    # Other domain policies must not be bloated into this prompt.
    assert "domain policy — programming" not in lower
    assert "domain policy — conceptual" not in lower
    assert "domain policy — mixed" not in lower
    assert "family a1" not in lower
    assert "family b — implementation" not in lower
    assert JSON_OUTPUT_SCHEMA.strip() in system
    assert "structural integrity" in lower


def test_realign_system_prompt_routes_programming_only() -> None:
    system = build_checklist_realign_system_prompt(domain="Programming")
    lower = system.lower()
    assert "domain policy — programming" in lower
    assert "artifact conflict rule" in lower
    assert "document.title" in lower
    assert "self-check before output (programming)" in lower
    assert "no accidental algebraic derivation" in lower
    assert "domain policy — stem" not in lower
    assert "stem application (default)" not in lower
    assert "domain policy — conceptual" not in lower


def test_realign_system_prompt_routes_conceptual_only() -> None:
    system = build_checklist_realign_system_prompt(domain="Conceptual")
    lower = system.lower()
    assert "domain policy — conceptual" in lower
    assert "conceptual case/argument" in lower
    assert "self-check before output (conceptual)" in lower
    assert "no accidental code or derivation" in lower
    assert "domain policy — programming" not in lower
    assert "artifact conflict rule" not in lower


def test_realign_system_prompt_routes_mixed_only() -> None:
    system = build_checklist_realign_system_prompt(domain="Mixed")
    lower = system.lower()
    assert "domain policy — mixed" in lower
    assert "route each checklist item locally" in lower or "routed locally" in lower
    assert "artificially balance" in lower
    assert "self-check before output (mixed)" in lower
    assert "domain policy — stem" not in lower
    assert "domain policy — programming" not in lower


def test_realign_system_prompt_unknown_domain_falls_back_to_mixed() -> None:
    system = build_checklist_realign_system_prompt(domain="")
    assert "DOMAIN POLICY — MIXED" in system


def test_realign_user_message_shape_is_domain_aware() -> None:
    draft = {
        "domain": "STEM",
        "topic_split": [{"id": "ts_1", "heading": "Widgets", "purpose": "Intro"}],
        "must_cover_checklist": [
            {
                "id": "mc_1",
                "concept": "WidgetLaw",
                "requirement": "Apply WidgetLaw",
                "priority": "required",
                "section_id": "ts_1",
                "depth_gate": "Named relation stated.",
            }
        ],
    }
    notes = (
        "- WidgetLaw: x = 2y\n"
        "- GadgetAPI.connect(timeout_ms): opens a session with timeout"
    )
    msg = build_checklist_realign_user_message(
        "Widget fundamentals",
        teaching_instruction="Cover WidgetLaw if relevant.",
        draft_plan=draft,
        research_notes=notes,
        domain="STEM",
    )
    assert "<topic>Widget fundamentals</topic>" in msg
    assert "<domain>STEM</domain>" in msg
    assert "<teaching_instruction>" in msg
    assert "WidgetLaw" in msg
    assert "GadgetAPI.connect(timeout_ms)" in msg
    assert "<draft_plan>" in msg
    assert json.dumps(draft, ensure_ascii=False) in msg
    assert "<research_notes>" in msg
    assert "Realign the JSON plan now for this STEM topic." in msg
    assert "not derivation in every section, and not code" in msg
    assert "vague fillers like 'specific values'" in msg


def test_realign_user_message_programming_closing() -> None:
    draft = {
        "domain": "Programming",
        "topic_split": [],
        "must_cover_checklist": [],
    }
    msg = build_checklist_realign_user_message(
        "Hooks",
        draft_plan=draft,
        research_notes="- useEffect",
    )
    assert "<domain>Programming</domain>" in msg
    assert "Realign the JSON plan now for this Programming topic." in msg
    assert "note-backed implementation gates" in msg
    assert "Artifact Conflict Rule" in msg


def test_truncate_research_notes_head_tail_with_marker() -> None:
    long_notes = "A" * 8_000 + "MID" + "B" * 8_000
    truncated = truncate_research_notes(long_notes, max_chars=100)
    assert "…[truncated]…" in truncated
    assert truncated.startswith("A")
    assert truncated.endswith("B")
    assert len(truncated) <= 100
