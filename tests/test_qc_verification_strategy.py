# tests/test_qc_verification_strategy.py
"""Unit tests for QC verification strategy (full vs targeted vs deterministic-only)."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    build_section_hashes,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.targeted_merge import (
    build_carried_forward_verification,
)
from src.api.utils.study_agent_utils.quality_check_utils.verification.qc_verification_strategy import (
    checks_safe_to_carry_forward,
    decide_qc_verification,
    prior_llm_checks,
    substance_certified,
)


def _section(section_id: str, *, content: str = "body") -> dict:
    return {
        "id": section_id,
        "heading": section_id,
        "content": content,
        "formula_blocks": [],
        "code_blocks": [],
        "subsections": [],
    }


def _doc(*sections: dict) -> dict:
    return {"sections": list(sections)}


def _llm_check(
    *,
    check_id: str = "mc_1",
    category: str = "must_cover",
    passed: bool = True,
    section_id: str = "ts_1",
) -> dict:
    return {
        "id": check_id,
        "category": category,
        "passed": passed,
        "severity": "critical",
        "section_id": section_id,
        "checklist_id": check_id,
        "evidence": "ok",
        "corrective_hint": "",
    }


def _placement_failure(*, section_id: str = "ts_2") -> dict:
    return {
        "id": "det_equation_in_content",
        "category": "block_placement",
        "passed": False,
        "severity": "major",
        "section_id": section_id,
        "evidence": "equation in prose",
        "corrective_hint": "move to formula block",
    }


def _certified_prior_qc_result(*, checks: list[dict] | None = None) -> dict:
    llm_checks = checks or [_llm_check()]
    return {
        "overall_status": "fail",
        "checks": llm_checks,
        "failed_checks": [],
        "hallucination_risk": "none",
        "is_refusal": False,
        "issues": [],
        "summary": "prior pass",
        "qc_llm_model_used": "test-model",
    }


class TestSubstanceCertified:
    def test_false_when_no_prior(self) -> None:
        assert substance_certified(None) is False

    def test_true_when_substance_passed(self) -> None:
        prior = _certified_prior_qc_result(
            checks=[
                _llm_check(),
                _llm_check(
                    check_id="content_accuracy_1",
                    category="content_accuracy",
                ),
            ]
        )
        assert substance_certified(prior) is True

    def test_false_when_must_cover_failed(self) -> None:
        prior = _certified_prior_qc_result(
            checks=[_llm_check(passed=False)],
        )
        assert substance_certified(prior) is False


class TestDecideQcVerification:
    def test_first_qc_always_full(self) -> None:
        decision = decide_qc_verification(
            qc_attempt=0,
            prior_qc_result=None,
            phase1_failures=[],
            is_targeted=False,
            document=_doc(_section("ts_1")),
            prior_hashes={},
        )
        assert decision.mode == "full"
        assert "first QC" in decision.reason

    def test_fixed_sections_always_targeted(self) -> None:
        decision = decide_qc_verification(
            qc_attempt=1,
            prior_qc_result=_certified_prior_qc_result(),
            phase1_failures=[_placement_failure()],
            is_targeted=True,
            document=_doc(_section("ts_1"), _section("ts_2")),
            prior_hashes=build_section_hashes(_doc(_section("ts_1"), _section("ts_2"))),
            state_reverify_section_ids=["ts_2"],
        )
        assert decision.mode == "targeted"
        assert decision.reverify_section_ids == ["ts_2"]

    def test_placement_only_certified_prior_deterministic_only(self) -> None:
        document = _doc(_section("ts_1"), _section("ts_2"))
        prior_hashes = build_section_hashes(document)
        decision = decide_qc_verification(
            qc_attempt=1,
            prior_qc_result=_certified_prior_qc_result(),
            phase1_failures=[_placement_failure(section_id="ts_2")],
            is_targeted=False,
            document=document,
            prior_hashes=prior_hashes,
        )
        assert decision.mode == "deterministic_only"
        assert decision.reverify_section_ids == []

    def test_patched_section_hash_changed_targeted(self) -> None:
        original = _doc(_section("ts_1"), _section("ts_2", content="original"))
        prior_hashes = build_section_hashes(original)
        patched = _doc(_section("ts_1"), _section("ts_2", content="patched"))
        decision = decide_qc_verification(
            qc_attempt=1,
            prior_qc_result=_certified_prior_qc_result(),
            phase1_failures=[_placement_failure(section_id="ts_2")],
            is_targeted=False,
            document=patched,
            prior_hashes=prior_hashes,
        )
        assert decision.mode == "targeted"
        assert decision.reverify_section_ids == ["ts_2"]

    def test_must_cover_fail_still_full(self) -> None:
        document = _doc(_section("ts_1"), _section("ts_2"))
        prior = _certified_prior_qc_result(
            checks=[_llm_check(passed=False)],
        )
        decision = decide_qc_verification(
            qc_attempt=1,
            prior_qc_result=prior,
            phase1_failures=[_placement_failure(section_id="ts_2")],
            is_targeted=False,
            document=document,
            prior_hashes=build_section_hashes(document),
        )
        assert decision.mode == "full"

    def test_structure_coverage_fail_full(self) -> None:
        document = _doc(_section("ts_1"))
        decision = decide_qc_verification(
            qc_attempt=1,
            prior_qc_result=_certified_prior_qc_result(),
            phase1_failures=[
                {
                    "id": "det_structure_coverage",
                    "category": "structure",
                    "passed": False,
                    "severity": "critical",
                    "evidence": "missing section",
                    "corrective_hint": "add section",
                }
            ],
            is_targeted=False,
            document=document,
            prior_hashes=build_section_hashes(document),
        )
        assert decision.mode == "full"


class TestChecksSafeToCarryForward:
    def test_drops_checks_for_changed_sections(self) -> None:
        original = _doc(_section("ts_1", content="v1"), _section("ts_2"))
        stored = build_section_hashes(original)
        changed = _doc(_section("ts_1", content="v2"), _section("ts_2"))
        checks = [
            _llm_check(section_id="ts_1"),
            _llm_check(check_id="mc_2", section_id="ts_2"),
        ]
        safe = checks_safe_to_carry_forward(checks, stored, changed)
        assert len(safe) == 1
        assert safe[0]["section_id"] == "ts_2"

    def test_carries_all_when_hashes_match(self) -> None:
        s1 = _section("ts_1")
        s2 = _section("ts_2")
        document = _doc(s1, s2)
        stored = build_section_hashes(document)
        checks = prior_llm_checks(
            _certified_prior_qc_result(
                checks=[_llm_check(), _llm_check(check_id="mc_2", section_id="ts_2")]
            )
        )
        safe = checks_safe_to_carry_forward(checks, stored, document)
        assert len(safe) == 2


class TestBuildCarriedForwardVerification:
    def test_shape_for_result_builder(self) -> None:
        prior = _certified_prior_qc_result()
        carried = [_llm_check()]
        verification = build_carried_forward_verification(prior, carried)
        assert verification["checks"] == carried
        assert verification["hallucination_risk"] == "none"
        assert verification["is_refusal"] is False
        assert "summary" in verification


class TestPriorLlmChecks:
    def test_excludes_det_checks(self) -> None:
        prior = {
            "checks": [
                _llm_check(),
                _placement_failure(),
            ]
        }
        llm_only = prior_llm_checks(prior)
        assert len(llm_only) == 1
        assert llm_only[0]["category"] == "must_cover"
