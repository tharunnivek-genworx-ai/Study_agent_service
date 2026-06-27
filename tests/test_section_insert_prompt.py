# tests/test_section_insert_prompt.py
"""Smoke tests for section insert prompt builder."""

from __future__ import annotations

from src.api.control.study_agent.prompts.section import section_insert_prompt

_MISSING_ITEMS = [
    {
        "id": "mc_3",
        "concept": "Polymorphism",
        "requirement": "Explain polymorphism with an example",
        "priority": "required",
    }
]


class TestSectionInsertPrompt:
    def test_user_message_includes_outline_and_missing_items(self):
        msg = section_insert_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            document_outline="- [mc_1] Intro\n- [mc_2] Encapsulation",
            missing_checklist_items=_MISSING_ITEMS,
        )
        assert "<topic>OOPS</topic>" in msg
        assert "<document_outline>" in msg
        assert "<missing_checklist_items>" in msg
        assert "mc_3" in msg
        assert "Polymorphism" in msg

    def test_system_prompt_requires_new_sections_only(self):
        system = section_insert_prompt.build_system_prompt(has_reference=False)
        assert "missing_checklist_items" in system
        assert '"sections"' in system

    def test_stem_domain_includes_stem_rules_only(self):
        system = section_insert_prompt.build_system_prompt(
            has_reference=False, domain="STEM"
        )
        assert "formula_blocks (never code_blocks)" in system
        assert "Programming: show complete runnable examples" not in system
        assert "Conceptual: use specific named cases" not in system
