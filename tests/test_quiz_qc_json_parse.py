# tests/test_quiz_qc_json_parse.py
"""Unit tests for quiz QC JSON parsing."""

from __future__ import annotations

import json

from src.api.utils.quiz_utils.quality_check_utils.parsing.json_parse import (
    is_valid_quiz_qc_response,
    parse_quiz_qc_response,
)


def _valid_quiz_qc() -> dict:
    return {
        "question_results": [
            {
                "question_id": "q-1",
                "question_number": 1,
                "answer_correctness_passed": True,
                "answer_evidence": "Independent answer: A. Marked option A matches.",
                "quality_passed": True,
                "quality_evidence": "Clear and on-topic.",
                "corrective_hint": "",
            }
        ],
        "quiz_summary": {
            "difficulty_ok": True,
            "difficulty_counts": {"easy": 1, "medium": 0, "hard": 0},
            "duplicate_concepts": [],
            "coverage_issues": [],
        },
        "wrong_answer_risk": "none",
        "corrective_instructions": "",
        "retry_recommendation": {
            "mode": "none",
            "failed_question_ids": [],
            "missing_concepts": [],
            "rationale": "",
        },
    }


class TestParseQuizQcResponse:
    def test_valid_json_parses(self):
        raw = json.dumps(_valid_quiz_qc())
        parsed = parse_quiz_qc_response(raw, question_count=1)
        assert parsed is not None
        assert parsed["wrong_answer_risk"] == "none"
        assert any(c["category"] == "difficulty_alignment" for c in parsed["checks"])

    def test_truncated_json_returns_none(self):
        raw = '{"question_results":[{"question_id":"q-1","question_number":1,"answer_correctness_passed":true,"answer_evidence":"Independent answer: A. Marked option A — matches."'
        assert parse_quiz_qc_response(raw) is None

    def test_missing_quiz_summary_invalid(self):
        obj = _valid_quiz_qc()
        del obj["quiz_summary"]
        assert is_valid_quiz_qc_response(obj) is False

    def test_missing_wrong_answer_risk_invalid(self):
        obj = _valid_quiz_qc()
        del obj["wrong_answer_risk"]
        assert is_valid_quiz_qc_response(obj) is False

    def test_legacy_checks_format_invalid(self):
        obj = {
            "checks": [
                {
                    "id": "answer_correctness_1",
                    "category": "answer_correctness",
                    "passed": True,
                }
            ],
            "quiz_summary": _valid_quiz_qc()["quiz_summary"],
            "wrong_answer_risk": "none",
            "corrective_instructions": "",
            "retry_recommendation": {"mode": "none"},
        }
        assert is_valid_quiz_qc_response(obj) is False
