# tests/test_hint_prompt.py
"""Smoke tests for hint prompt builder."""

from __future__ import annotations

from src.api.control.hint_agent.prompts import hint_prompt

HINT_PROGRAMMING_ANCHOR = "Focus on how Python handles integer division"
HINT_STEM_ANCHOR = "Think about how kinetic energy scales with velocity"


class TestHintPrompt:
    def test_build_hint_system_prompt_empty_domain_matches_static_alias(self):
        assert (
            hint_prompt.build_hint_system_prompt(domain="")
            == hint_prompt.SYSTEM_PROMPT_HINT
        )

    def test_build_hint_system_prompt_mixed_domain_matches_empty_domain(self):
        empty = hint_prompt.build_hint_system_prompt(domain="")
        mixed = hint_prompt.build_hint_system_prompt(domain="Mixed")
        assert empty == mixed

    def test_stem_domain_includes_stem_reasoning_only(self):
        system = hint_prompt.build_hint_system_prompt(domain="STEM")
        assert HINT_STEM_ANCHOR in system
        assert HINT_PROGRAMMING_ANCHOR not in system
        assert "Consider what problem this policy was" not in system

    def test_build_hint_prompt_passes_topic_and_domain(self):
        payload = hint_prompt.build_hint_prompt(
            questions_for_hinting=[
                {
                    "question_id": "q1",
                    "question_text": "What is 2+2?",
                    "option_a": "3",
                    "option_b": "4",
                    "option_c": "5",
                    "option_d": "6",
                    "correct_option": "B",
                    "explanation": "Basic addition.",
                }
            ],
            topic_title="Arithmetic",
            domain="STEM",
        )
        assert "Arithmetic" in payload["user_message"]
        assert "<domain>\nSTEM\n</domain>" in payload["user_message"]
        assert HINT_STEM_ANCHOR in payload["system_prompt"]
        assert HINT_PROGRAMMING_ANCHOR not in payload["system_prompt"]

    def test_regeneration_appends_regenerate_rules(self):
        system = hint_prompt.build_hint_system_prompt(domain="", is_regeneration=True)
        assert "RULE — REGENERATION MODE" in system
