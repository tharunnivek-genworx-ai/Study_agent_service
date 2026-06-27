# tests/test_quiz_qc_scoring.py
"""Unit tests for quiz QC scoring."""

from __future__ import annotations

from src.api.utils.quiz_utils.quality_check_utils.results.quiz_scoring import (
    derive_quiz_overall_status,
    is_quiz_qc_deliverable,
)


def _check(
    *,
    category: str = "topic_relevance",
    passed: bool = True,
    severity: str = "major",
) -> dict:
    return {
        "id": f"{category}_1",
        "category": category,
        "question": "test?",
        "passed": passed,
        "severity": severity,
        "evidence": "",
        "corrective_hint": "",
    }


class TestDeriveQuizOverallStatus:
    def test_all_pass_no_risk(self):
        checks = [_check(passed=True)]
        assert derive_quiz_overall_status(checks, "none") == "pass"

    def test_high_wrong_answer_risk_fails(self):
        checks = [_check(passed=True)]
        assert derive_quiz_overall_status(checks, "high") == "fail"

    def test_critical_failure_fails(self):
        checks = [_check(passed=False, severity="critical")]
        assert derive_quiz_overall_status(checks, "none") == "fail"


class TestIsQuizQcDeliverable:
    def test_warn_deliverable_without_critical_failures(self):
        failed = [_check(category="question_quality", passed=False, severity="major")]
        assert is_quiz_qc_deliverable(
            overall_status="warn",
            failed_checks=failed,
            wrong_answer_risk="low",
        )

    def test_answer_correctness_failure_not_deliverable(self):
        failed = [
            _check(
                category="answer_correctness",
                passed=False,
                severity="critical",
            )
        ]
        assert not is_quiz_qc_deliverable(
            overall_status="warn",
            failed_checks=failed,
            wrong_answer_risk="low",
        )

    def test_high_risk_warn_not_deliverable(self):
        assert not is_quiz_qc_deliverable(
            overall_status="warn",
            failed_checks=[],
            wrong_answer_risk="high",
        )

    def test_missing_concepts_with_mode_none_and_pass_is_deliverable(self):
        assert is_quiz_qc_deliverable(
            overall_status="pass",
            failed_checks=[],
            wrong_answer_risk="none",
            retry_recommendation={
                "mode": "none",
                "missing_concepts": ["Recursion"],
            },
        )
