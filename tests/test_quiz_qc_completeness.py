# tests/test_quiz_qc_completeness.py
"""Unit tests for quiz QC response completeness validation."""

from __future__ import annotations

import json

from src.api.utils.quiz_utils.quality_check_utils.parsing.json_parse import (
    expand_quiz_summary_to_checks,
    expected_quiz_qc_check_count,
    expected_quiz_qc_question_result_count,
    is_valid_quiz_qc_response,
    normalize_quiz_qc_response,
    parse_quiz_qc_response,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_scoring import (
    is_quiz_qc_deliverable,
)


def _question_result(question_number: int, question_id: str | None = None) -> dict:
    return {
        "question_id": question_id or f"q-{question_number}",
        "question_number": question_number,
        "answer_correctness_passed": True,
        "answer_evidence": "Independent answer: A. Marked option A matches.",
        "quality_passed": True,
        "quality_evidence": "Clear and on-topic.",
        "corrective_hint": "",
    }


def _quiz_summary(*, difficulty_ok: bool = True) -> dict:
    return {
        "difficulty_ok": difficulty_ok,
        "difficulty_counts": {"easy": 3, "medium": 4, "hard": 3},
        "duplicate_concepts": [],
        "coverage_issues": [],
    }


def _complete_qc_response(question_count: int) -> dict:
    return {
        "question_results": [
            _question_result(qnum) for qnum in range(1, question_count + 1)
        ],
        "quiz_summary": _quiz_summary(),
        "wrong_answer_risk": "none",
        "corrective_instructions": "",
        "retry_recommendation": {
            "mode": "none",
            "failed_question_ids": [],
            "missing_concepts": [],
            "rationale": "",
        },
    }


class TestExpectedQuizQcCheckCount:
    def test_ten_questions_expects_ten_question_results(self):
        assert expected_quiz_qc_question_result_count(10) == 10

    def test_ten_questions_expects_twenty_normalized_checks(self):
        assert expected_quiz_qc_check_count(10) == 20


class TestQuizQcCompleteness:
    def test_truncated_response_rejected_for_question_count(self):
        truncated = _complete_qc_response(10)
        truncated["question_results"] = truncated["question_results"][:5]
        assert is_valid_quiz_qc_response(truncated, question_count=10) is False

    def test_complete_response_accepted_for_ten_questions(self):
        complete = _complete_qc_response(10)
        assert is_valid_quiz_qc_response(complete, question_count=10) is True

    def test_parse_rejects_incomplete_response(self):
        incomplete = _complete_qc_response(10)
        incomplete["question_results"] = incomplete["question_results"][:5]
        raw = json.dumps(incomplete)
        assert parse_quiz_qc_response(raw, question_count=10) is None

    def test_normalize_expands_quiz_summary_to_synthetic_checks(self):
        normalized = normalize_quiz_qc_response(_complete_qc_response(2))
        categories = {check["category"] for check in normalized["checks"]}
        assert "difficulty_alignment" in categories
        assert "duplicate_overlap" in categories
        assert len(normalized["checks"]) == 6  # 4 per-question + 2 synthetic

    def test_expand_quiz_summary_marks_duplicate_failure(self):
        summary = _quiz_summary()
        summary["duplicate_concepts"] = ["useState basics"]
        checks = expand_quiz_summary_to_checks(summary)
        duplicate = next(c for c in checks if c["category"] == "duplicate_overlap")
        assert duplicate["passed"] is False


class TestMissingConceptsDeliverable:
    def test_missing_concepts_ignored_when_all_checks_pass(self):
        assert is_quiz_qc_deliverable(
            overall_status="pass",
            failed_checks=[],
            wrong_answer_risk="none",
            retry_recommendation={
                "mode": "none",
                "missing_concepts": ["Recursion"],
            },
        )
