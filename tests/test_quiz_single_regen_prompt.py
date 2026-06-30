# tests/test_quiz_single_regen_prompt.py
"""Smoke tests for quiz single-question regen prompt builder."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts import quiz_single_regen_prompt
from src.api.control.quiz_agent.prompts.quiz_graph.quiz_prompt import (
    OUTPUT_FORMAT_BLOCK,
    build_domain_classification_block,
)

_SAMPLE_QUESTIONS = [
    {
        "question_id": "q-1",
        "question_text": "What is inheritance?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "B",
        "explanation": "Because B.",
        "difficulty": "easy",
        "topic_tag": "OOP basics",
        "order_index": 0,
    },
    {
        "question_id": "q-2",
        "question_text": "What is encapsulation?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
        "explanation": "Because A.",
        "difficulty": "medium",
        "topic_tag": "OOP basics",
        "order_index": 1,
    },
]


class TestQuizSingleRegenPrompt:
    def test_system_prompt_includes_shared_blocks_and_vague_guard(self):
        system = quiz_single_regen_prompt.build_system_prompt(domain="")
        assert build_domain_classification_block(domain="").strip() in system
        assert OUTPUT_FORMAT_BLOCK.strip() in system
        assert "hints_stale" in system
        assert "rework_status" in system
        assert "VAGUE FEEDBACK CHECK" in system
        assert "ACTION 1 — REVISE WORDING" in system
        assert "ACTION 3 — REPLACE WHOLE QUESTION" in system

    def test_stem_domain_excludes_programming_question_rules(self):
        empty = quiz_single_regen_prompt.build_system_prompt(domain="")
        stem = quiz_single_regen_prompt.build_system_prompt(domain="STEM")
        assert empty != stem
        assert "Never define the same method" not in stem

    def test_user_message_includes_context_and_feedback(self):
        msg = quiz_single_regen_prompt.build_user_message(
            topic_title="OOPS",
            study_material_content="Study material body.",
            difficulty_profile="mixed",
            mentor_feedback="Make distractors harder for the encapsulation question.",
            question_ids=["q-2"],
            questions=_SAMPLE_QUESTIONS,
            domain="Programming",
            topic_split=[
                {"id": "ts_1", "heading": "Encapsulation", "purpose": "Hide state"}
            ],
        )
        assert "<study_material>" in msg
        assert "<quiz_outline>" in msg
        assert "<questions_to_rework>" in msg
        assert "<mentor_feedback>" in msg
        assert "Make distractors harder" in msg
        assert "<topic_split>" in msg
        block = msg.split("<questions_to_rework>")[1].split("</questions_to_rework>")[0]
        parsed = json.loads(block.strip())
        assert parsed[0]["question_id"] == "q-2"
        assert parsed[0]["current_question_json"]["question_text"] == (
            "What is encapsulation?"
        )

    def test_build_prompt_returns_system_and_user(self):
        payload = quiz_single_regen_prompt.build_quiz_single_regen_prompt(
            topic_title="OOPS",
            study_material_content="Body.",
            difficulty_profile="mixed",
            mentor_feedback="Simplify the stem wording on q-1.",
            question_ids=["q-1"],
            questions=_SAMPLE_QUESTIONS,
            domain="Programming",
        )
        assert "system_prompt" in payload
        assert "user_message" in payload
        assert "q-1" in payload["user_message"]

    def test_user_message_includes_quiz_outline_not_questions_to_fix(self):
        msg = quiz_single_regen_prompt.build_user_message(
            topic_title="OOPS",
            study_material_content="Study material body.",
            difficulty_profile="mixed",
            mentor_feedback="Replace distractors on q-2 with harder misconceptions.",
            question_ids=["q-2"],
            questions=_SAMPLE_QUESTIONS,
            domain="Programming",
        )
        assert "<quiz_outline>" in msg
        assert "<questions_to_rework>" in msg
        assert "<questions_to_fix>" not in msg
        assert "<domain>" in msg
        assert "<difficulty_profile>" in msg
