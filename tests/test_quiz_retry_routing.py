# tests/test_quiz_retry_routing.py
"""Unit tests for quiz QC retry routing."""

from __future__ import annotations

from src.api.utils.quiz_utils.quality_check_utils.results.quiz_retry_routing import (
    classify_quiz_retry_routing,
)


def _question(question_id: str) -> dict:
    return {
        "question_id": question_id,
        "question_text": f"Question {question_id}?",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
        "explanation": "Because A.",
        "order_index": 0,
    }


def _failed_check(
    *,
    category: str,
    question_id: str | None = None,
    severity: str = "major",
) -> dict:
    check = {
        "id": f"{category}_1",
        "category": category,
        "question": "test?",
        "passed": False,
        "severity": severity,
        "evidence": "failed",
        "corrective_hint": "fix it",
    }
    if question_id:
        check["question_id"] = question_id
    return check


class TestClassifyQuizRetryRouting:
    def test_no_failures_returns_none(self):
        result = classify_quiz_retry_routing(
            {"checks": [], "failed_checks": []},
            [_question("q1")],
        )
        assert result.mode == "none"

    def test_single_question_failure_patches(self):
        qc_result = {
            "checks": [_failed_check(category="question_quality", question_id="q1")],
            "failed_checks": [
                _failed_check(category="question_quality", question_id="q1")
            ],
            "wrong_answer_risk": "none",
        }
        result = classify_quiz_retry_routing(qc_result, [_question("q1")])
        assert result.mode == "question_patch"
        assert result.failed_question_ids == ["q1"]

    def test_missing_concepts_insert(self):
        qc_result = {
            "checks": [_failed_check(category="duplicate_overlap", question_id=None)],
            "failed_checks": [
                _failed_check(category="duplicate_overlap", question_id=None)
            ],
            "retry_recommendation": {
                "mode": "question_insert",
                "missing_concepts": ["Recursion"],
            },
            "wrong_answer_risk": "none",
        }
        result = classify_quiz_retry_routing(qc_result, [_question("q1")])
        assert result.mode == "question_insert"
        assert "Recursion" in result.missing_concepts

    def test_four_failed_questions_force_full_regeneration(self):
        questions = [_question(f"q{i}") for i in range(1, 6)]
        failed = [
            _failed_check(category="question_quality", question_id=f"q{i}")
            for i in range(1, 5)
        ]
        qc_result = {
            "checks": failed,
            "failed_checks": failed,
            "wrong_answer_risk": "none",
        }
        result = classify_quiz_retry_routing(qc_result, questions)
        assert result.mode == "full_regeneration"
