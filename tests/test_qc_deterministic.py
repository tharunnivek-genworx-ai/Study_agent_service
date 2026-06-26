# tests/test_qc_deterministic.py
"""Unit tests for deterministic QC extraction from JSON study documents."""

from __future__ import annotations

import json

from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    build_code_review_payloads,
    extract_structure,
    structure_check,
)

_GOOD_DOC = json.dumps(
    {
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
                            "        self._balance = balance\n"
                            "\n"
                            "    def get_balance(self):\n"
                            "        return self._balance"
                        ),
                    }
                ],
            },
        ]
    }
)

_EXAMPLE_SECTION_DOC = json.dumps(
    {
        "sections": [
            {
                "id": "mc_mistakes",
                "heading": "Common Mistakes",
                "content": "Broken on purpose:",
                "code_blocks": [{"language": "python", "code": "class Car:\n    ..."}],
            }
        ]
    }
)

_CHECKLIST = [
    {
        "id": "mc_1",
        "priority": "required",
        "concept": "Intro",
        "requirement": "Define OOPS",
    },
    {
        "id": "mc_2",
        "priority": "required",
        "concept": "Encapsulation",
        "requirement": "Explain hiding",
    },
]


class TestExtractStructure:
    def test_finds_code_artifacts(self):
        structure = extract_structure(_GOOD_DOC)
        assert len(structure.code_artifacts) == 1
        assert structure.code_artifacts[0].id == "code_1"
        assert structure.code_artifacts[0].language == "python"
        assert structure.code_artifacts[0].fenced_code.startswith("```python")

    def test_fenced_code_includes_fence_markers(self):
        structure = extract_structure(_GOOD_DOC)
        art = structure.code_artifacts[0]
        assert art.fenced_code.startswith("```")
        assert art.fenced_code.endswith("```")
        assert "class BankAccount" in art.fenced_code

    def test_sections_have_ids(self):
        structure = extract_structure(_GOOD_DOC)
        assert len(structure.sections) == 2
        assert structure.sections[0]["id"] == "mc_1"
        assert structure.sections[1]["id"] == "mc_2"

    def test_no_preamble_for_json_documents(self):
        structure = extract_structure(_GOOD_DOC)
        assert structure.has_preamble is False

    def test_finds_subsection_code_artifacts(self):
        doc = json.dumps(
            {
                "sections": [
                    {
                        "id": "ts_3",
                        "heading": "Inheritance",
                        "content": "Overview.",
                        "subsections": [
                            {
                                "heading": "Single Inheritance",
                                "content": "One parent.",
                                "code_blocks": [
                                    {
                                        "language": "python",
                                        "code": "class Child(Parent):\n    pass",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        structure = extract_structure(doc)
        assert len(structure.code_artifacts) == 1
        assert structure.code_artifacts[0].subsection_heading == "Single Inheritance"
        assert structure.code_artifacts[0].section_id == "ts_3"


class TestBuildCodeReviewPayloads:
    def test_payload_includes_section_id(self):
        structure = extract_structure(_GOOD_DOC)
        payloads = build_code_review_payloads(structure)
        assert len(payloads) == 1
        assert payloads[0]["section_id"] == "mc_2"
        assert payloads[0]["section_heading"] == "Encapsulation"

    def test_mistakes_section_type(self):
        structure = extract_structure(_EXAMPLE_SECTION_DOC)
        payloads = build_code_review_payloads(structure)
        assert payloads[0]["section_type"] == "mistakes"

    def test_payload_includes_subsection_heading(self):
        doc = json.dumps(
            {
                "sections": [
                    {
                        "id": "ts_3",
                        "heading": "Inheritance",
                        "subsections": [
                            {
                                "heading": "Single Inheritance",
                                "code_blocks": [{"language": "python", "code": "pass"}],
                            }
                        ],
                    }
                ]
            }
        )
        structure = extract_structure(doc)
        payloads = build_code_review_payloads(structure)
        assert payloads[0]["subsection_heading"] == "Single Inheritance"


class TestStructureCheck:
    def test_passes_when_required_ids_present(self):
        structure = extract_structure(_GOOD_DOC)
        doc = json.loads(_GOOD_DOC)
        assert structure_check(structure, checklist=_CHECKLIST, doc=doc) is None

    def test_fails_when_required_id_missing(self):
        partial = json.dumps(
            {
                "sections": [
                    {
                        "id": "mc_1",
                        "heading": "Introduction",
                        "content": "OOPS is important.",
                    }
                ]
            }
        )
        structure = extract_structure(partial)
        doc = json.loads(partial)
        result = structure_check(structure, checklist=_CHECKLIST, doc=doc)
        assert result is not None
        assert result["passed"] is False
        assert "mc_2" in result["evidence"]
