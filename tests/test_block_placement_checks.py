# tests/test_block_placement_checks.py
"""Unit tests for deterministic block-placement QC checks."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)

_CLEAN_PROGRAMMING_DOC = {
    "sections": [
        {
            "id": "mc_1",
            "heading": "Introduction",
            "content": "OOPS is important.",
        },
        {
            "id": "mc_2",
            "heading": "Encapsulation",
            "content": "Encapsulation hides details.",
            "code_blocks": [
                {
                    "language": "python",
                    "code": (
                        "class BankAccount:\n"
                        "    def __init__(self, balance):\n"
                        "        self._balance = balance"
                    ),
                    "explanation": "Demonstrates a simple encapsulated balance field.",
                }
            ],
        },
    ]
}


def _check_ids(checks: list[dict]) -> set[str]:
    return {str(c.get("id")) for c in checks}


class TestBlockPlacementChecks:
    def test_clean_programming_doc_has_no_failures(self):
        checks = block_placement_checks(
            _CLEAN_PROGRAMMING_DOC,
            domain="Programming",
            checklist=[],
        )
        assert checks == []

    def test_pseudocode_in_code_block_fails(self):
        doc = {
            "sections": [
                {
                    "id": "ts_3",
                    "heading": "Inheritance",
                    "code_blocks": [
                        {
                            "language": "python",
                            "code": "if (need[i] <= work) then\n    assign job",
                            "explanation": "Pseudocode example.",
                        }
                    ],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="Programming", checklist=[])
        assert "det_pseudocode_in_code_block" in _check_ids(checks)

    def test_math_language_in_code_block_fails(self):
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
        checks = block_placement_checks(doc, domain="STEM", checklist=[])
        assert "det_math_in_code_block" in _check_ids(checks)

    def test_equation_in_content_fails_for_stem(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Derivatives",
                    "content": (
                        "The derivative is f'(x) = lim_{h \\to 0} "
                        "\\frac{f(x+h)-f(x)}{h}."
                    ),
                }
            ]
        }
        checks = block_placement_checks(doc, domain="STEM", checklist=[])
        assert "det_equation_in_content" in _check_ids(checks)

    def test_code_in_formula_block_fails(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Bad block",
                    "formula_blocks": [
                        {
                            "notation": "plain",
                            "formula": "def foo():\n    return 1",
                            "explanation": "Not an equation.",
                        }
                    ],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="STEM", checklist=[])
        assert "det_code_in_formula_block" in _check_ids(checks)

    def test_empty_block_explanation_fails(self):
        doc = {
            "sections": [
                {
                    "id": "mc_2",
                    "heading": "Encapsulation",
                    "code_blocks": [
                        {"language": "python", "code": "x = 1", "explanation": ""}
                    ],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="Programming", checklist=[])
        assert "det_empty_block_explanation" in _check_ids(checks)

    def test_conceptual_has_blocks_fails(self):
        doc = {
            "sections": [
                {
                    "id": "mc_1",
                    "heading": "Ethics",
                    "content": "Overview.",
                    "code_blocks": [
                        {
                            "language": "python",
                            "code": "print('hi')",
                            "explanation": "Should not be here.",
                        }
                    ],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="Conceptual", checklist=[])
        assert "det_conceptual_has_blocks" in _check_ids(checks)

    def test_stem_derivation_missing_formula_fails(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Derivatives",
                    "content": "Derivation explained in prose only.",
                    "code_blocks": [
                        {
                            "language": "python",
                            "code": "x = 1",
                            "explanation": "Not a derivation.",
                        }
                    ],
                }
            ]
        }
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "requirement": "Define the derivative",
                "depth_gate": "step-by-step derivation",
            }
        ]
        checks = block_placement_checks(doc, domain="STEM", checklist=checklist)
        assert "det_stem_derivation_missing_formula" in _check_ids(checks)
        assert "det_stem_code_substitutes_derivation" in _check_ids(checks)

    def test_stem_code_substitutes_derivation_fails_with_formula_blocks(self):
        """Python alongside formula_blocks still fails when checklist demands derivation."""
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Types of Integrals",
                    "content": "Definite and indefinite integrals.",
                    "formula_blocks": [
                        {
                            "notation": "LaTeX",
                            "formula": "\\int_a^b f(x) dx",
                            "explanation": "Definite integral notation.",
                        }
                    ],
                    "code_blocks": [
                        {
                            "language": "python",
                            "code": (
                                "from scipy.integrate import quad\n"
                                "quad(lambda x: x**2, 0, 1)"
                            ),
                            "explanation": "Numerically evaluates an integral.",
                        }
                    ],
                }
            ]
        }
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_2",
                "requirement": (
                    "Derive the formula for the definite integral using the limit definition."
                ),
                "depth_gate": (
                    "Derivation begins from the limit definition; each algebraic "
                    "step shown explicitly; correct final result reached."
                ),
            }
        ]
        checks = block_placement_checks(doc, domain="STEM", checklist=checklist)
        ids = _check_ids(checks)
        assert "det_stem_code_substitutes_derivation" in ids
        assert "det_stem_derivation_missing_formula" not in ids
        code_check = next(
            c for c in checks if c.get("id") == "det_stem_code_substitutes_derivation"
        )
        assert code_check.get("section_id") == "ts_2"
        assert code_check.get("severity") == "critical"

    def test_stem_code_allowed_without_derivation_checklist(self):
        doc = {
            "sections": [
                {
                    "id": "ts_6",
                    "heading": "Numerical Integration",
                    "content": "Approximation methods.",
                    "code_blocks": [
                        {
                            "language": "python",
                            "code": "import numpy as np",
                            "explanation": "Sets up numerical integration.",
                        }
                    ],
                }
            ]
        }
        checklist = [
            {
                "id": "mc_5",
                "section_id": "ts_6",
                "requirement": "Explain the trapezoidal rule.",
                "depth_gate": "Rule stated with a worked numeric example.",
            }
        ]
        checks = block_placement_checks(doc, domain="STEM", checklist=checklist)
        assert "det_stem_code_substitutes_derivation" not in _check_ids(checks)

    def test_stem_code_substitutes_derivation_scans_subsection_blocks(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Wave-Particle Duality",
                    "subsections": [
                        {
                            "heading": "Derivation",
                            "code_blocks": [
                                {
                                    "language": "python",
                                    "code": "import numpy as np",
                                    "explanation": "Plots a wave function.",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_2",
                "requirement": "Derive the wave function expression.",
                "depth_gate": "step-by-step derivation from de Broglie hypothesis",
            }
        ]
        checks = block_placement_checks(doc, domain="STEM", checklist=checklist)
        assert "det_stem_code_substitutes_derivation" in _check_ids(checks)

    def test_subsection_blocks_are_scanned(self):
        doc = {
            "sections": [
                {
                    "id": "ts_3",
                    "heading": "Inheritance",
                    "subsections": [
                        {
                            "heading": "Single Inheritance",
                            "code_blocks": [
                                {
                                    "language": "python",
                                    "code": "if (x) then y",
                                    "explanation": "Bad pseudocode.",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="Programming", checklist=[])
        assert "det_pseudocode_in_code_block" in _check_ids(checks)
        assert checks[0].get("section_id") == "ts_3"

    def test_failed_checks_have_section_id_and_critical_severity(self):
        doc = {
            "sections": [
                {
                    "id": "mc_2",
                    "heading": "Encapsulation",
                    "code_blocks": [{"language": "python", "code": "x = 1"}],
                }
            ]
        }
        checks = block_placement_checks(doc, domain="Programming", checklist=[])
        assert checks
        for check in checks:
            assert check["passed"] is False
            assert check["severity"] == "critical"
            assert check["category"] == "document_coherence"
            assert check.get("section_id") == "mc_2"
