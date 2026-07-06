# tests/test_block_placement_remediation.py
"""Unit tests for deterministic block-placement remediation."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation import (
    apply_relocation_plans,
    build_relocation_plans,
    relocation_plans_for_llm_fallback,
)


def _check_ids(checks: list[dict]) -> set[str]:
    return {str(c.get("id")) for c in checks}


class TestBlockPlacementRemediation:
    def test_ts2_dereference_when_limit_definition_in_formula_blocks(self):
        doc = {
            "sections": [
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
                }
            ]
        }
        failures = block_placement_checks(doc, domain="STEM", checklist=[])
        # Tier 2: bare f'(x) in prose should not fail placement checks.
        assert "det_equation_in_content" not in _check_ids(failures)

        forced_failures = [
            {
                "id": "det_equation_in_content",
                "section_id": "ts_2",
                "evidence": "Section 'Derivatives': Prose contains display-math patterns",
            }
        ]
        plans = build_relocation_plans(doc, forced_failures, domain="STEM")
        patched, report = apply_relocation_plans(doc, plans)
        content = patched["sections"][0]["content"]
        assert "f'(x)" not in content
        assert "the derivative" in content
        assert report.fixed_section_ids == ["ts_2"]

    def test_ts3_extract_power_rule_clause_from_prose(self):
        doc = {
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
        failures = block_placement_checks(doc, domain="STEM", checklist=[])
        assert "det_equation_in_content" in _check_ids(failures)

        plans = build_relocation_plans(doc, failures, domain="STEM")
        patched, report = apply_relocation_plans(doc, plans)
        section = patched["sections"][0]
        assert "f'(x) = nx^(n-1)" not in section["content"]
        assert section["formula_blocks"]
        assert any(
            "nx^(n-1)" in str(block.get("formula", ""))
            for block in section["formula_blocks"]
        )
        assert report.fixed_section_ids == ["ts_3"]
        assert not block_placement_checks(patched, domain="STEM", checklist=[])

    def test_math_in_code_block_moves_to_formula_blocks(self):
        doc = {
            "sections": [
                {
                    "id": "ts_1",
                    "heading": "Limits",
                    "code_blocks": [
                        {
                            "language": "Math",
                            "code": "lim x→a f(x) = L",
                            "explanation": "Limit notation.",
                        }
                    ],
                }
            ]
        }
        failures = block_placement_checks(doc, domain="STEM", checklist=[])
        plans = build_relocation_plans(doc, failures, domain="STEM")
        patched, report = apply_relocation_plans(doc, plans)
        section = patched["sections"][0]
        assert not section.get("code_blocks")
        assert section["formula_blocks"][0]["formula"] == "lim x→a f(x) = L"
        assert report.fixed_section_ids == ["ts_1"]

    def test_apply_twice_is_idempotent(self):
        doc = {
            "sections": [
                {
                    "id": "ts_3",
                    "heading": "Power Rule",
                    "content": "if f(x) = x^n, then f'(x) = nx^(n-1).",
                    "formula_blocks": [],
                }
            ]
        }
        failures = block_placement_checks(doc, domain="STEM", checklist=[])
        plans = build_relocation_plans(doc, failures, domain="STEM")
        patched_once, _ = apply_relocation_plans(doc, plans)
        plans_again = build_relocation_plans(
            patched_once,
            block_placement_checks(patched_once, domain="STEM", checklist=[]),
            domain="STEM",
        )
        patched_twice, report = apply_relocation_plans(patched_once, plans_again)
        assert len(patched_twice["sections"][0]["formula_blocks"]) == len(
            patched_once["sections"][0]["formula_blocks"]
        )
        assert not report.fixed_section_ids or report.fixed_section_ids == []

    def test_evidence_with_apostrophe_in_heading_parses_subsection(self):
        doc = {
            "sections": [
                {
                    "id": "ts_4",
                    "heading": "L'Hôpital's Rule",
                    "subsections": [
                        {
                            "heading": "Example",
                            "content": "if f(x) = g(x)/h(x) then apply the rule.",
                        }
                    ],
                }
            ]
        }
        failures = [
            {
                "id": "det_equation_in_content",
                "section_id": "ts_4",
                "evidence": (
                    "Section \"L'Hôpital's Rule\", subsection 'Example': "
                    "Prose contains display-math patterns"
                ),
            }
        ]
        plans = build_relocation_plans(doc, failures, domain="STEM")
        assert plans
        assert plans[0].relocations
        assert plans[0].relocations[0].subsection_heading == "Example"

    def test_relocation_plans_for_llm_fallback_includes_unresolved_high_confidence(
        self,
    ):
        plans = build_relocation_plans(
            {
                "sections": [
                    {
                        "id": "ts_3",
                        "heading": "Power Rule",
                        "content": "if f(x) = x^n, then f'(x) = nx^(n-1).",
                        "formula_blocks": [],
                    }
                ]
            },
            [
                {
                    "id": "det_equation_in_content",
                    "section_id": "ts_3",
                    "evidence": "Section 'Power Rule': Prose contains display-math patterns",
                }
            ],
            domain="STEM",
        )
        remaining = [
            {
                "id": "det_equation_in_content",
                "section_id": "ts_3",
                "evidence": "still failing",
            }
        ]
        payload = relocation_plans_for_llm_fallback(
            plans,
            needs_llm_fallback=True,
            remaining_placement_failures=remaining,
        )
        assert payload is not None
        assert any(item["section_id"] == "ts_3" for item in payload)
