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
    EVIDENCE_FAMILY_BLOCK,
)

_POLICY_KEYWORDS = (
    "edit budget",
    "anti-bloat",
    "do not import every note",
    "evidence catalog",
    "outline spine",
    "note artifact binding",
    "draft-debt sweep",
    "section load",
    "rewrite-in-place",
    "equation / relation priority",
    "note artifact",
    "family a1",
    "family b",
    "family c",
    "depth_gate skeleton",
    "preserve domain",
    "max(3",
)


def test_realign_system_prompt_has_compact_policy_and_domain_reuse() -> None:
    system = build_checklist_realign_system_prompt()
    lower = system.lower()
    assert DOMAIN_REUSE_FROM_DRAFT_PLAN_BLOCK in system
    assert "never reclassify" in lower
    for keyword in _POLICY_KEYWORDS:
        assert keyword in lower, f"missing policy keyword: {keyword}"
    assert "requirement skeleton" in lower
    assert "hard word ban" in lower
    assert "structural integrity" in lower
    # Draft is outline spine only — old primary-authority phrasing must be gone.
    assert "authoritative spine" not in lower


def test_realign_system_prompt_keeps_evidence_family_skeletons() -> None:
    system = build_checklist_realign_system_prompt()
    assert "FAMILY A1 — MATHEMATICAL" in system
    assert "FAMILY A2 — MATHEMATICAL" in system
    assert "FAMILY B — IMPLEMENTATION" in system
    assert "FAMILY C — INTERPRETIVE" in system
    assert "At most +1 new topic_split" in system or "+1 new topic_split" in system
    assert "A2 FILL RULE" in system
    assert "standard classroom instance of the named note relation" in system
    assert "Never invent a new measurement framework" in system


def test_shared_a2_fill_guidance_prefers_named_relation() -> None:
    assert "A2 FILL GUIDANCE" in EVIDENCE_FAMILY_BLOCK
    assert "named quantities symbolically" in EVIDENCE_FAMILY_BLOCK
    assert "standard classroom instance of that named relation" in EVIDENCE_FAMILY_BLOCK
    assert "unrelated measurement framework or parameter class" in EVIDENCE_FAMILY_BLOCK


def test_realign_user_message_shape() -> None:
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
    )
    assert "<topic>Widget fundamentals</topic>" in msg
    assert "<teaching_instruction>" in msg
    assert "WidgetLaw" in msg
    assert "GadgetAPI.connect(timeout_ms)" in msg
    assert "<draft_plan>" in msg
    assert json.dumps(draft, ensure_ascii=False) in msg
    assert "<research_notes>" in msg
    assert "Realign the JSON plan now." in msg
    assert "evidence catalog" in msg
    assert "Bind each required gate to a note-backed artifact" in msg
    assert "Sweep unsupported draft debt" in msg
    assert "section already owns 2 items" in msg


def test_truncate_research_notes_head_tail_with_marker() -> None:
    long_notes = "A" * 8_000 + "MID" + "B" * 8_000
    truncated = truncate_research_notes(long_notes, max_chars=100)
    assert "…[truncated]…" in truncated
    assert truncated.startswith("A")
    assert truncated.endswith("B")
    assert len(truncated) <= 100
