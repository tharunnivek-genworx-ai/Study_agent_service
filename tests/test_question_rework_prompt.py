# tests/test_question_rework_prompt.py
"""Smoke tests for question rework prompt builder."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts import question_rework_prompt
from src.api.control.quiz_agent.prompts.quiz_graph.quiz_prompt import (
    OUTPUT_FORMAT_BLOCK,
    build_domain_classification_block,
)

_SAMPLE_QUESTIONS = [
    {
        "question_id": "q-2",
        "question_text": "What is encapsulation?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
        "explanation": "Because A.",
        "order_index": 1,
    }
]

_QUESTION_FAILURES = [
    {
        "question_id": "q-2",
        "failures": [
            {
                "category": "answer_correctness",
                "evidence": "Marked option is wrong.",
                "corrective_hint": "Fix the correct option.",
            }
        ],
    }
]


class TestQuestionReworkPrompt:
    def test_system_prompt_includes_shared_blocks(self):
        system = question_rework_prompt.build_system_prompt(domain="")
        assert build_domain_classification_block(domain="").strip() in system
        assert OUTPUT_FORMAT_BLOCK.strip() in system
        assert "hints_stale" in system

    def test_stem_domain_excludes_programming_question_rules(self):
        empty = question_rework_prompt.build_system_prompt(domain="")
        stem = question_rework_prompt.build_system_prompt(domain="STEM")
        assert empty != stem
        assert "Never define the same method" not in stem

    def test_user_message_includes_questions_to_fix_and_preserves_id_contract(self):
        msg = question_rework_prompt.build_user_message(
            topic_title="OOPS",
            study_material_content="Study material body.",
            difficulty_profile="mixed",
            question_failures=_QUESTION_FAILURES,
            questions=_SAMPLE_QUESTIONS,
            domain="Programming",
        )
        assert "<questions_to_fix>" in msg
        assert "q-2" in msg
        assert "Fix the correct option." in msg
        block = msg.split("<questions_to_fix>")[1].split("</questions_to_fix>")[0]
        parsed = json.loads(block.strip())
        assert parsed[0]["question_id"] == "q-2"
        assert parsed[0]["failures"][0]["category"] == "answer_correctness"
