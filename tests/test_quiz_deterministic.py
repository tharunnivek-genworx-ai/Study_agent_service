# tests/test_quiz_deterministic.py
"""Unit tests for quiz deterministic QC checks."""

from __future__ import annotations

from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    det_question_count,
    det_quiz_coherence,
    run_deterministic_quiz_checks,
)


def _sample_question(**overrides) -> dict:
    base = {
        "question_id": "q-1",
        "question_text": "What is X?",
        "option_a": "A1",
        "option_b": "B1",
        "option_c": "C1",
        "option_d": "D1",
        "correct_option": "A",
        "explanation": "Because A is correct.",
    }
    base.update(overrides)
    return base


class TestDetQuestionCount:
    def test_count_match_passes(self):
        check = det_question_count([_sample_question()], expected_count=1)
        assert check["passed"] is True

    def test_count_mismatch_fails(self):
        check = det_question_count([_sample_question()], expected_count=3)
        assert check["passed"] is False
        assert check["severity"] == "critical"


class TestDetQuizCoherence:
    def test_invalid_correct_option_fails(self):
        checks = det_quiz_coherence([_sample_question(correct_option="Z")])
        assert any(not c["passed"] for c in checks)

    def test_duplicate_stem_fails(self):
        q1 = _sample_question(question_id="q-1", question_text="Same stem?")
        q2 = _sample_question(question_id="q-2", question_text="Same stem?")
        checks = det_quiz_coherence([q1, q2])
        assert any(
            c["category"] == "duplicate_overlap" and not c["passed"] for c in checks
        )

    def test_blank_explanation_fails(self):
        checks = det_quiz_coherence([_sample_question(explanation="")])
        assert any(not c["passed"] for c in checks)

    def test_missing_option_c_fails_critical(self):
        checks = det_quiz_coherence([_sample_question(option_c=None)])
        assert any(
            c["id"].startswith("det_missing_option_c_d") and not c["passed"]
            for c in checks
        )

    def test_all_four_options_present_no_missing_c_d_fail(self):
        checks = det_quiz_coherence([_sample_question()])
        assert not any(c["id"].startswith("det_missing_option_c_d") for c in checks)


class TestRunDeterministicQuizChecks:
    def test_returns_count_and_coherence_checks(self):
        checks = run_deterministic_quiz_checks(
            [_sample_question()],
            expected_count=1,
        )
        assert checks[0]["id"] == "det_question_count"
        assert len(checks) >= 1
