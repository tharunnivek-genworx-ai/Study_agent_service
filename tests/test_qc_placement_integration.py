# tests/test_qc_placement_integration.py
"""Integration: placement-only Calculus-like failures avoid full_regeneration loops."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.qc_retry_audit import (
    retry_feedback_channel,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation import (
    apply_relocation_plans,
    build_relocation_plans,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    classify_retry_routing,
)

_CALCULUS_CHECKLIST = [
    {
        "id": "mc_1",
        "section_id": "ts_1",
        "concept": "Limits",
        "requirement": "Cover limits",
        "priority": "required",
    },
    {
        "id": "mc_2",
        "section_id": "ts_2",
        "concept": "Derivatives",
        "requirement": "Cover derivatives",
        "priority": "required",
    },
    {
        "id": "mc_3",
        "section_id": "ts_3",
        "concept": "Power rule",
        "requirement": "Cover the power rule",
        "priority": "required",
    },
]

_CALCULUS_DOC = {
    "sections": [
        {"id": "ts_1", "heading": "Limits", "content": "Limits are foundational."},
        {
            "id": "ts_2",
            "heading": "Derivatives",
            "content": (
                "The derivative of a function f(x) is denoted as f'(x) and "
                "is defined as the limit of the difference quotient."
            ),
            "formula_blocks": [
                {
                    "notation": "Limit Definition",
                    "formula": "f'(x) = lim(h → 0) [f(x + h) - f(x)]/h",
                    "explanation": "Limit definition of the derivative.",
                }
            ],
        },
        {
            "id": "ts_3",
            "heading": "Power Rule",
            "content": (
                "The power rule states that if f(x) = x^n, then f'(x) = nx^(n-1)."
            ),
            "formula_blocks": [],
        },
    ]
}


def _check(**kwargs) -> dict:
    return {
        "passed": False,
        "severity": "critical",
        "question": "",
        "evidence": "",
        "corrective_hint": "",
        **kwargs,
    }


def _qc_result_from_placement_failures(
    document: dict,
    *,
    checklist: list[dict],
) -> dict:
    placement_failures = block_placement_checks(
        document,
        domain="STEM",
        checklist=checklist,
    )
    checks = [
        _check(
            id=item["id"],
            category="must_cover",
            checklist_id=item["id"],
            passed=True,
            section_id=item["section_id"],
        )
        for item in checklist
    ]
    checks.extend(placement_failures)
    return {"checks": checks, "failed_checks": placement_failures}


class TestCalculusPlacementIntegration:
    def test_three_qc_attempts_never_escalate_to_full_regeneration(self):
        """Regression for run_20260706_155710: det-only failures stay section_patch."""
        document = _CALCULUS_DOC
        modes: list[str] = []

        for _attempt in range(3):
            qc_result = _qc_result_from_placement_failures(
                document,
                checklist=_CALCULUS_CHECKLIST,
            )
            routing = classify_retry_routing(
                qc_result,
                document,
                _CALCULUS_CHECKLIST,
            )
            modes.append(routing.mode)

            if routing.mode == "none":
                break
            assert routing.mode == "section_patch"
            assert routing.failure_class == "placement_only"
            assert retry_feedback_channel(routing.mode) == "structured_section_failures"

            placement_failures = qc_result["failed_checks"]
            plans = build_relocation_plans(
                document,
                placement_failures,
                domain="STEM",
            )
            document, report = apply_relocation_plans(document, plans)
            if report.all_resolved:
                break

        assert modes
        assert "full_regeneration" not in modes
        assert block_placement_checks(document, domain="STEM", checklist=[]) == []

    def test_placement_only_routing_after_partial_remediation(self):
        """If one section still fails after remediation, routing remains section_patch."""
        document = {
            "sections": [
                {
                    "id": "ts_3",
                    "heading": "Power Rule",
                    "content": (
                        "The power rule states that if f(x) = x^n, then f'(x) = nx^(n-1)."
                    ),
                    "formula_blocks": [],
                }
            ]
        }
        checklist = [_CALCULUS_CHECKLIST[2]]
        qc_result = _qc_result_from_placement_failures(document, checklist=checklist)
        routing = classify_retry_routing(qc_result, document, checklist)
        assert routing.mode == "section_patch"
        assert routing.failure_class == "placement_only"

        plans = build_relocation_plans(
            document,
            qc_result["failed_checks"],
            domain="STEM",
        )
        patched, report = apply_relocation_plans(document, plans)
        assert report.fixed_section_ids == ["ts_3"]
        assert not block_placement_checks(patched, domain="STEM", checklist=[])

        post_qc = _qc_result_from_placement_failures(patched, checklist=checklist)
        post_routing = classify_retry_routing(post_qc, patched, checklist)
        assert post_routing.mode == "none"
