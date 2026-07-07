# tests/test_placement_false_positive_fixes.py
"""Regression tests for placement false positives and mixed retry routing."""

from __future__ import annotations

import json

from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    split_section_failures_by_kind,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation import (
    apply_relocation_plans,
    build_relocation_plans,
    run_placement_remediation_phase,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.placement_patterns import (
    extract_equation_core,
    is_narrative_equation_clause,
    looks_like_programming_code_in_formula,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    classify_retry_routing,
)


def _check_ids(checks: list[dict]) -> set[str]:
    return {str(c.get("id")) for c in checks}


class TestProgrammingCodeDetection:
    def test_math_prose_with_function_f_is_not_programming_code(self):
        samples = [
            "For example, let's calculate the limit of the function f(x) = (x^2 - 4) / (x - 2) as x approaches 2",
            "The definite integral of a function f(x) from a to b is denoted as ∫[a, b] f(x) dx",
            "lim_{x→2} (x + 2) = 4",
        ]
        for sample in samples:
            assert not looks_like_programming_code_in_formula(sample)

    def test_real_programming_syntax_still_detected(self):
        assert looks_like_programming_code_in_formula("def foo():\n    return 1")
        assert looks_like_programming_code_in_formula("function calculate() {")
        assert looks_like_programming_code_in_formula("import numpy as np")


class TestNarrativeEquationExtraction:
    def test_narrative_clause_detected(self):
        clause = (
            "For example, let's calculate the limit of the function "
            "f(x) = (x^2 - 4) / (x - 2) as x approaches 2"
        )
        assert is_narrative_equation_clause(clause)
        assert extract_equation_core(clause) == "f(x) = (x^2 - 4) / (x - 2)"

    def test_compact_equation_not_narrative(self):
        clause = "if f(x) = x^n, then f'(x) = nx^(n-1)."
        assert not is_narrative_equation_clause(clause)


class TestCalculusPhase1bRegression:
    def test_phase1b_clears_placement_without_code_in_formula_false_positive(self):
        doc = {
            "sections": [
                {
                    "id": "ts_1",
                    "heading": "Introduction to Limits",
                    "content": "Limits are foundational in calculus.",
                    "subsections": [
                        {
                            "heading": "Calculating Limits",
                            "content": (
                                "To calculate the limit of a function, we can use the "
                                "definition of a limit. For example, let's calculate the "
                                "limit of the function f(x) = (x^2 - 4) / (x - 2) as x "
                                "approaches 2."
                            ),
                            "formula_blocks": [],
                        }
                    ],
                },
                {
                    "id": "ts_4",
                    "heading": "Integrals",
                    "content": (
                        "The definite integral of a function f(x) from a to b is denoted "
                        "as ∫[a, b] f(x) dx and is defined as the limit of the sum."
                    ),
                    "formula_blocks": [],
                },
            ]
        }
        remediation = run_placement_remediation_phase(
            doc,
            domain="STEM",
            checklist=[],
            optional_structure_check=None,
            generated_content=json.dumps(doc),
        )
        failures = remediation.block_placement_failures
        assert "det_code_in_formula_block" not in _check_ids(failures)
        assert not failures

    def test_relocated_formula_blocks_use_equation_core_only(self):
        doc = {
            "sections": [
                {
                    "id": "ts_1",
                    "heading": "Introduction to Limits",
                    "subsections": [
                        {
                            "heading": "Calculating Limits",
                            "content": (
                                "For example, let's calculate the limit of the function "
                                "f(x) = (x^2 - 4) / (x - 2) as x approaches 2."
                            ),
                            "formula_blocks": [],
                        }
                    ],
                }
            ]
        }
        failures = block_placement_checks(doc, domain="STEM", checklist=[])
        plans = build_relocation_plans(doc, failures, domain="STEM")
        patched, _report = apply_relocation_plans(doc, plans)
        formula = patched["sections"][0]["subsections"][0]["formula_blocks"][0][
            "formula"
        ]
        assert formula == "f(x) = (x^2 - 4) / (x - 2)"
        assert "function f" not in formula.lower() or formula.startswith("f(x)")


class TestMixedRetryRoutingSplit:
    def test_split_section_failures_by_kind(self):
        bundles = [
            {
                "section_id": "ts_1",
                "failures": [{"check_id": "det_code_in_formula_block"}],
            },
            {
                "section_id": "ts_5",
                "failures": [{"check_id": "mc_5", "category": "must_cover"}],
            },
        ]
        placement, substance = split_section_failures_by_kind(bundles)
        assert [b["section_id"] for b in placement] == ["ts_1"]
        assert [b["section_id"] for b in substance] == ["ts_5"]

    def test_classify_retry_routing_populates_split_bundles(self):
        qc_result = {
            "failed_checks": [
                {
                    "id": "det_code_in_formula_block",
                    "category": "document_coherence",
                    "passed": False,
                    "section_id": "ts_1",
                    "evidence": "Section 'Introduction to Limits': formula_blocks body contains programming keywords",
                    "corrective_hint": "Move programming code into code_blocks.",
                },
                {
                    "id": "content_accuracy_1",
                    "category": "content_accuracy",
                    "passed": False,
                    "section_id": "ts_5",
                    "evidence": "missing worked example",
                    "corrective_hint": "add example",
                },
            ]
        }
        document = {
            "sections": [
                {"id": "ts_1", "heading": "Introduction to Limits", "content": "x"},
                {"id": "ts_5", "heading": "Applications", "content": "y"},
            ]
        }
        routing = classify_retry_routing(qc_result, document, checklist=[])
        assert routing.failure_class == "mixed"
        assert len(routing.placement_section_failures) == 1
        assert routing.placement_section_failures[0]["section_id"] == "ts_1"
        assert len(routing.substance_section_failures) == 1
        assert routing.substance_section_failures[0]["section_id"] == "ts_5"
