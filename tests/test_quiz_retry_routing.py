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
            "checks": [
                {
                    "id": "duplicate_overlap",
                    "category": "duplicate_overlap",
                    "question": "coverage?",
                    "passed": False,
                    "severity": "major",
                    "evidence": "duplicates=[]; coverage=['Recursion']",
                    "corrective_hint": "Add coverage",
                }
            ],
            "failed_checks": [
                {
                    "id": "duplicate_overlap",
                    "category": "duplicate_overlap",
                    "question": "coverage?",
                    "passed": False,
                    "severity": "major",
                    "evidence": "duplicates=[]; coverage=['Recursion']",
                    "corrective_hint": "Add coverage",
                }
            ],
            "quiz_summary": {
                "difficulty_ok": True,
                "difficulty_counts": {"easy": 1, "medium": 0, "hard": 0},
                "duplicate_concepts": [],
                "coverage_issues": ["Recursion"],
            },
            "retry_recommendation": {
                "mode": "question_insert",
                "missing_concepts": ["Recursion"],
            },
            "wrong_answer_risk": "none",
        }
        result = classify_quiz_retry_routing(qc_result, [_question("q1")])
        assert result.mode == "question_insert"
        assert result.missing_concepts == ["Recursion"]
        assert not any(
            concept.startswith("duplicates=") for concept in result.missing_concepts
        )

    def test_duplicate_overlap_evidence_blob_is_not_a_missing_concept(self):
        evidence = "duplicates=[]; coverage=['The Battle of Stalingrad']"
        qc_result = {
            "checks": [
                {
                    "id": "duplicate_overlap",
                    "category": "duplicate_overlap",
                    "question": "coverage?",
                    "passed": False,
                    "severity": "major",
                    "evidence": evidence,
                    "corrective_hint": "Add coverage",
                }
            ],
            "failed_checks": [
                {
                    "id": "duplicate_overlap",
                    "category": "duplicate_overlap",
                    "question": "coverage?",
                    "passed": False,
                    "severity": "major",
                    "evidence": evidence,
                    "corrective_hint": "Add coverage",
                }
            ],
            "quiz_summary": {
                "coverage_issues": ["The Battle of Stalingrad"],
            },
            "retry_recommendation": {
                "mode": "question_patch",
                "failed_question_ids": ["q3"],
                "missing_concepts": [
                    "The Battle of Stalingrad",
                    evidence,
                ],
            },
            "wrong_answer_risk": "none",
        }
        questions = [_question(f"q{i}") for i in range(1, 9)]
        # Also fail a per-question check so mode can be patch_then_insert.
        qc_result["failed_checks"].append(
            _failed_check(category="answer_correctness", question_id="q3")
        )
        qc_result["checks"].append(
            _failed_check(category="answer_correctness", question_id="q3")
        )
        result = classify_quiz_retry_routing(qc_result, questions)
        assert result.mode == "question_patch_then_insert"
        assert result.missing_concepts == ["The Battle of Stalingrad"]
        assert result.failed_question_ids == ["q3"]

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

    def test_single_answer_correctness_failure_on_ten_question_quiz_patches(self):
        questions = [_question(f"q{i}") for i in range(1, 11)]
        qc_result = {
            "checks": [_failed_check(category="answer_correctness", question_id="q7")],
            "failed_checks": [
                _failed_check(category="answer_correctness", question_id="q7")
            ],
            "wrong_answer_risk": "low",
            "retry_recommendation": {
                "mode": "question_patch",
                "failed_question_ids": ["q7"],
                "missing_concepts": [],
                "rationale": "One question has an incorrect answer",
            },
        }
        result = classify_quiz_retry_routing(qc_result, questions)
        assert result.mode == "question_patch"
        assert result.failed_question_ids == ["q7"]

    def test_llm_full_regeneration_does_not_override_question_patch(self):
        questions = [_question(f"q{i}") for i in range(1, 11)]
        qc_result = {
            "checks": [_failed_check(category="answer_correctness", question_id="q7")],
            "failed_checks": [
                _failed_check(category="answer_correctness", question_id="q7")
            ],
            "wrong_answer_risk": "low",
            "retry_recommendation": {
                "mode": "full_regeneration",
                "failed_question_ids": ["q7"],
                "missing_concepts": [],
                "rationale": "Rewrite the whole quiz",
            },
        }
        result = classify_quiz_retry_routing(qc_result, questions)
        assert result.mode == "question_patch"
        assert result.failed_question_ids == ["q7"]
