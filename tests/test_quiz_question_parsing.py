# tests/test_quiz_question_parsing.py
"""Unit tests for quiz LLM output parsing."""

from __future__ import annotations

import json

from src.api.utils.quiz_utils.generation.question_parsing import parse_json_array


def _question_payload() -> dict:
    return {
        "question_text": "What is X?",
        "option_a": "A1",
        "option_b": "B1",
        "option_c": "C1",
        "option_d": "D1",
        "correct_option": "A",
        "explanation": "Because A.",
        "difficulty": "easy",
        "domain": "STEM",
        "topic_tag": "ts_1",
    }


class TestParseJsonArray:
    def test_parses_json_object_wrapper(self):
        raw = json.dumps({"questions": [_question_payload()]})
        items = parse_json_array(raw, expected_count=1)
        assert len(items) == 1
        assert items[0]["question_text"] == "What is X?"

    def test_parses_legacy_bare_array(self):
        raw = json.dumps([_question_payload()])
        items = parse_json_array(raw, expected_count=1)
        assert len(items) == 1

    def test_accepts_under_count_for_retry(self):
        raw = json.dumps({"questions": [_question_payload()]})
        items = parse_json_array(raw, expected_count=3)
        assert len(items) == 1

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({"questions": [_question_payload()]}) + "\n```"
        items = parse_json_array(raw, expected_count=1)
        assert len(items) == 1

    def test_trims_excess_questions_when_expected_count_set(self):
        raw = json.dumps({"questions": [_question_payload() for _ in range(4)]})
        items = parse_json_array(raw, expected_count=2)
        assert len(items) == 2
