# tests/test_quiz_qc_prompt.py
"""Smoke tests for quiz QC prompt builder."""

from __future__ import annotations

from src.api.control.quiz_agent.prompts import quiz_qc_prompt


class TestQuizQcPrompt:
    def test_build_system_prompt_empty_domain_matches_static_alias(self):
        assert (
            quiz_qc_prompt.build_system_prompt(domain="")
            == quiz_qc_prompt.SYSTEM_PROMPT
        )

    def test_build_system_prompt_mixed_domain_uses_classification_stub(self):
        mixed = quiz_qc_prompt.build_system_prompt(domain="Mixed")
        assert "`Mixed` is authoritative; do not reclassify." in mixed
        assert "classify each question by what it actually tests" not in mixed

    def test_known_domain_uses_classification_stub(self):
        system = quiz_qc_prompt.build_system_prompt(domain="STEM")
        assert "`STEM` is authoritative; do not reclassify." in system
        assert "classify each question by what it actually tests" not in system

    def test_empty_domain_includes_full_classification(self):
        system = quiz_qc_prompt.build_system_prompt(domain="")
        assert "classify each question by what it actually tests" in system
        assert "STEP 2 — PRODUCE ONE question_result PER QUESTION" in system
        assert "Quiz-only answerability" in system
        assert "Embedded artifact format" in system

    def test_user_message_includes_domain(self):
        msg = quiz_qc_prompt.build_user_message(
            topic_title="Calculus",
            difficulty="medium",
            question_count=2,
            generation_mode="generate",
            study_material_content="Limits and derivatives.",
            quiz_questions=[{"question_id": "q1"}],
            domain="STEM",
        )
        assert "<domain>\nSTEM\n</domain>" in msg
