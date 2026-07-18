# tests/test_qc_scoring.py
"""Unit tests for qc_scoring — no LLM required."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    derive_overall_status,
    derive_scores,
    extract_failed_checks,
    is_qc_deliverable,
    public_scores,
    sanitize_retry_recommendation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(
    id: str = "c1",
    category: str = "content_accuracy",
    passed: bool = True,
    severity: str = "critical",
    question: str = "Is X correct?",
    evidence: str = "",
    corrective_hint: str = "",
) -> dict:
    return {
        "id": id,
        "category": category,
        "question": question,
        "passed": passed,
        "severity": severity,
        "evidence": evidence,
        "corrective_hint": corrective_hint,
    }


# ---------------------------------------------------------------------------
# derive_overall_status
# ---------------------------------------------------------------------------


class TestDeriveOverallStatus:
    def test_all_checks_pass_no_risk(self):
        checks = [_check(passed=True), _check(id="c2", passed=True)]
        assert derive_overall_status(checks, "none", False) == "pass"

    def test_all_checks_pass_low_risk(self):
        checks = [_check(passed=True)]
        assert derive_overall_status(checks, "low", False) == "pass"

    def test_empty_checks_no_risk(self):
        assert derive_overall_status([], "none", False) == "pass"

    def test_one_critical_fail_returns_fail(self):
        checks = [_check(passed=False, severity="critical")]
        assert derive_overall_status(checks, "none", False) == "fail"

    def test_critical_fail_overrides_medium_risk(self):
        # critical fail trumps medium risk — result is still fail
        checks = [_check(passed=False, severity="critical")]
        assert derive_overall_status(checks, "medium", False) == "fail"

    def test_high_hallucination_risk_returns_fail(self):
        checks = [_check(passed=True)]
        assert derive_overall_status(checks, "high", False) == "fail"

    def test_high_risk_with_all_passing_still_fails(self):
        checks = [_check(passed=True), _check(id="c2", passed=True)]
        assert derive_overall_status(checks, "high", False) == "fail"

    def test_one_major_fail_no_critical_returns_warn(self):
        checks = [
            _check(id="c1", passed=True, severity="critical"),
            _check(id="c2", passed=False, severity="major"),
        ]
        assert derive_overall_status(checks, "none", False) == "warn"

    def test_medium_risk_no_fails_returns_warn(self):
        checks = [_check(passed=True)]
        assert derive_overall_status(checks, "medium", False) == "warn"

    def test_minor_fail_only_returns_warn(self):
        checks = [_check(passed=False, severity="minor")]
        assert derive_overall_status(checks, "none", False) == "warn"

    def test_is_refusal_always_pass(self):
        # Even with critical fails and high risk, refusal → pass
        checks = [_check(passed=False, severity="critical")]
        assert derive_overall_status(checks, "high", True) == "pass"

    def test_is_refusal_empty_checks(self):
        assert derive_overall_status([], "none", True) == "pass"

    def test_mixed_severities_critical_fail_is_fail(self):
        checks = [
            _check(id="c1", passed=False, severity="major"),
            _check(id="c2", passed=False, severity="critical"),
            _check(id="c3", passed=True, severity="critical"),
        ]
        assert derive_overall_status(checks, "low", False) == "fail"

    def test_all_major_fails_no_critical_is_warn(self):
        checks = [
            _check(id="c1", passed=False, severity="major"),
            _check(id="c2", passed=False, severity="major"),
        ]
        assert derive_overall_status(checks, "low", False) == "warn"


# ---------------------------------------------------------------------------
# is_qc_deliverable
# ---------------------------------------------------------------------------


class TestIsQcDeliverable:
    def test_pass_status_is_deliverable(self):
        assert is_qc_deliverable(
            overall_status="pass",
            failed_checks=[],
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_refusal_is_deliverable(self):
        assert is_qc_deliverable(
            overall_status="fail",
            failed_checks=[_check(passed=False, severity="critical")],
            hallucination_risk="high",
            is_refusal=True,
        )

    def test_fail_status_not_deliverable(self):
        assert not is_qc_deliverable(
            overall_status="fail",
            failed_checks=[_check(passed=False, severity="critical")],
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_warn_major_only_is_deliverable(self):
        assert is_qc_deliverable(
            overall_status="warn",
            failed_checks=[_check(passed=False, severity="major")],
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_warn_with_critical_fail_not_deliverable(self):
        assert not is_qc_deliverable(
            overall_status="warn",
            failed_checks=[_check(passed=False, severity="critical")],
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_warn_medium_hallucination_no_critical_is_deliverable(self):
        assert is_qc_deliverable(
            overall_status="warn",
            failed_checks=[_check(passed=False, severity="major")],
            hallucination_risk="medium",
            is_refusal=False,
        )

    def test_warn_high_hallucination_not_deliverable(self):
        assert not is_qc_deliverable(
            overall_status="warn",
            failed_checks=[_check(passed=False, severity="major")],
            hallucination_risk="high",
            is_refusal=False,
        )

    def test_unknown_status_not_deliverable(self):
        assert not is_qc_deliverable(
            overall_status="unknown",
            failed_checks=[],
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_warn_failed_must_cover_not_deliverable(self):
        assert not is_qc_deliverable(
            overall_status="warn",
            failed_checks=[
                _check(
                    id="mc_4",
                    category="must_cover",
                    passed=False,
                    severity="major",
                ),
                _check(
                    id="teaching_alignment",
                    category="teaching_alignment",
                    passed=False,
                    severity="major",
                ),
            ],
            hallucination_risk="low",
            is_refusal=False,
            retry_recommendation={
                "mode": "section_patch",
                "failed_section_ids": ["ts_3"],
                "missing_checklist_ids": ["mc_4"],
            },
        )

    def test_warn_teaching_alignment_only_still_deliverable(self):
        assert is_qc_deliverable(
            overall_status="warn",
            failed_checks=[
                _check(
                    id="teaching_alignment",
                    category="teaching_alignment",
                    passed=False,
                    severity="major",
                ),
            ],
            hallucination_risk="low",
            is_refusal=False,
        )

    def test_warn_missing_checklist_ids_not_deliverable(self):
        # Raw recommendation still blocks; callers must sanitize first
        # (build_final_qc_result / classify_retry_routing do that).
        assert not is_qc_deliverable(
            overall_status="warn",
            failed_checks=[],
            hallucination_risk="none",
            is_refusal=False,
            retry_recommendation={
                "mode": "section_insert",
                "failed_section_ids": [],
                "missing_checklist_ids": ["mc_5"],
            },
        )

    def test_pass_with_sanitized_empty_recommendation_is_deliverable(self):
        assert is_qc_deliverable(
            overall_status="pass",
            failed_checks=[],
            hallucination_risk="none",
            is_refusal=False,
            retry_recommendation={
                "mode": "none",
                "failed_section_ids": [],
                "missing_checklist_ids": [],
                "rationale": "Sanitized contradictory retry_recommendation.",
            },
        )


# ---------------------------------------------------------------------------
# sanitize_retry_recommendation
# ---------------------------------------------------------------------------


class TestSanitizeRetryRecommendation:
    def test_calvin_style_contradiction_cleared_to_none(self):
        """All checks pass + spurious missing/patch targets → mode none."""
        checklist = [
            {
                "id": "mc_3",
                "concept": "Regeneration",
                "section_id": "ts_3",
                "priority": "required",
            }
        ]
        document = {
            "sections": [
                {"id": "ts_3", "heading": "Regen", "content": "has content"},
            ]
        }
        checks = [
            {
                "id": "mc_3",
                "category": "must_cover",
                "checklist_id": "mc_3",
                "section_id": "ts_3",
                "passed": True,
                "severity": "critical",
            }
        ]
        sanitized = sanitize_retry_recommendation(
            {
                "mode": "section_patch",
                "failed_section_ids": ["ts_3"],
                "missing_checklist_ids": ["mc_3"],
                "rationale": "Needs ATP values",
            },
            checks=checks,
            document=document,
            checklist=checklist,
        )
        assert sanitized is not None
        assert sanitized["mode"] == "none"
        assert sanitized["failed_section_ids"] == []
        assert sanitized["missing_checklist_ids"] == []
        assert is_qc_deliverable(
            overall_status="pass",
            failed_checks=[],
            hallucination_risk="low",
            is_refusal=False,
            retry_recommendation=sanitized,
        )

    def test_keeps_true_missing_when_section_absent(self):
        checklist = [
            {
                "id": "mc_5",
                "concept": "Missing topic",
                "section_id": "ts_5",
                "priority": "required",
            }
        ]
        document = {"sections": [{"id": "ts_1", "heading": "Intro", "content": "x"}]}
        checks = [
            {
                "id": "mc_5",
                "category": "must_cover",
                "checklist_id": "mc_5",
                "section_id": "ts_5",
                "passed": False,
                "severity": "critical",
            }
        ]
        sanitized = sanitize_retry_recommendation(
            {
                "mode": "section_insert",
                "failed_section_ids": [],
                "missing_checklist_ids": ["mc_5"],
                "rationale": "Section absent",
            },
            checks=checks,
            document=document,
            checklist=checklist,
        )
        assert sanitized is not None
        assert sanitized["mode"] == "section_insert"
        assert sanitized["missing_checklist_ids"] == ["mc_5"]

    def test_keeps_failed_section_when_check_failed(self):
        checklist = [
            {
                "id": "mc_2",
                "concept": "Fixation",
                "section_id": "ts_2",
                "priority": "required",
            }
        ]
        document = {
            "sections": [{"id": "ts_2", "heading": "Fixation", "content": "thin"}]
        }
        checks = [
            {
                "id": "mc_2",
                "category": "must_cover",
                "checklist_id": "mc_2",
                "section_id": "ts_2",
                "passed": False,
                "severity": "critical",
            }
        ]
        sanitized = sanitize_retry_recommendation(
            {
                "mode": "section_patch",
                "failed_section_ids": ["ts_2"],
                "missing_checklist_ids": [],
                "rationale": "Depth gate miss",
            },
            checks=checks,
            document=document,
            checklist=checklist,
        )
        assert sanitized is not None
        assert sanitized["mode"] == "section_patch"
        assert sanitized["failed_section_ids"] == ["ts_2"]


class TestDeriveScores:
    def test_empty_checks_all_none(self):
        scores = derive_scores([])
        for key in (
            "structure",
            "content_accuracy",
            "code_quality",
            "section_depth",
            "teaching_alignment",
        ):
            assert scores[key] is None

    def test_readability_always_none(self):
        scores = derive_scores([_check(category="content_accuracy", passed=True)])
        assert "readability" not in scores or scores.get("readability") is None

    def test_all_pass_score_is_10(self):
        checks = [
            _check(id="c1", category="content_accuracy", passed=True),
            _check(id="c2", category="content_accuracy", passed=True),
        ]
        scores = derive_scores(checks)
        assert scores["content_accuracy"] == 10

    def test_all_fail_score_is_1(self):
        checks = [
            _check(id="c1", category="structure", passed=False),
            _check(id="c2", category="structure", passed=False),
        ]
        scores = derive_scores(checks)
        assert scores["structure"] == 1

    def test_half_pass_score_is_5(self):
        checks = [
            _check(id="c1", category="teaching_alignment", passed=True),
            _check(id="c2", category="teaching_alignment", passed=False),
        ]
        scores = derive_scores(checks)
        assert scores["teaching_alignment"] == 5

    def test_section_depth_aggregates_pitfalls_and_concept_and_must_cover(self):
        checks = [
            _check(id="c1", category="pitfalls_depth", passed=True),
            _check(id="c2", category="pitfalls_depth", passed=False),
            _check(id="c3", category="concept_coverage", passed=True),
            _check(id="c4", category="must_cover", passed=True),
        ]
        # 3 out of 4 passed → round(3/4 * 10) = round(7.5) = 8
        scores = derive_scores(checks)
        assert scores["section_depth"] == round(3 / 4 * 10)

    def test_code_quality_checks_map_correctly(self):
        checks = [
            _check(id="c1", category="code_quality", passed=True),
            _check(id="c2", category="code_quality", passed=True),
            _check(id="c3", category="code_quality", passed=False),
        ]
        # 2 out of 3 → round(2/3 * 10) = round(6.67) = 7
        scores = derive_scores(checks)
        assert scores["code_quality"] == round(2 / 3 * 10)

    def test_stack_fidelity_maps_to_code_quality_score(self):
        checks = [
            _check(id="c1", category="code_quality", passed=True),
            _check(id="c2", category="stack_fidelity", passed=False),
        ]
        scores = derive_scores(checks)
        assert scores["code_quality"] == round(1 / 2 * 10)

    def test_unknown_category_ignored(self):
        checks = [_check(id="c1", category="unknown_category", passed=False)]
        scores = derive_scores(checks)
        # Unknown category does not affect any score; section_depth still None
        assert scores["section_depth"] is None

    def test_score_clamped_to_minimum_1(self):
        # Single failing check — score must be at least 1, not 0
        checks = [_check(id="c1", category="structure", passed=False)]
        scores = derive_scores(checks)
        assert scores["structure"] >= 1

    def test_score_clamped_to_maximum_10(self):
        checks = [_check(id="c1", category="structure", passed=True)]
        scores = derive_scores(checks)
        assert scores["structure"] <= 10


# ---------------------------------------------------------------------------
# public_scores
# ---------------------------------------------------------------------------


class TestPublicScores:
    def test_strips_structure_and_readability(self):
        raw = {
            "structure": 1,
            "readability": None,
            "content_accuracy": 8,
            "code_quality": 9,
            "section_depth": 7,
            "teaching_alignment": 10,
        }
        public = public_scores(raw)
        assert "structure" not in public
        assert "readability" not in public
        assert public == {
            "content_accuracy": 8,
            "code_quality": 9,
            "section_depth": 7,
            "teaching_alignment": 10,
        }


# ---------------------------------------------------------------------------
# extract_failed_checks
# ---------------------------------------------------------------------------


class TestExtractFailedChecks:
    def test_empty_returns_empty(self):
        assert extract_failed_checks([]) == []

    def test_all_passed_returns_empty(self):
        checks = [_check(passed=True), _check(id="c2", passed=True)]
        assert extract_failed_checks(checks) == []

    def test_returns_only_failed(self):
        passing = _check(id="c1", passed=True)
        failing = _check(id="c2", passed=False)
        result = extract_failed_checks([passing, failing])
        assert result == [failing]

    def test_preserves_full_check_dict(self):
        c = _check(
            id="c1",
            passed=False,
            severity="critical",
            evidence="GIL described incorrectly",
            corrective_hint="Rewrite GIL section",
        )
        result = extract_failed_checks([c])
        assert result[0]["evidence"] == "GIL described incorrectly"
        assert result[0]["corrective_hint"] == "Rewrite GIL section"
