# tests/test_study_generation_json.py
"""Unit tests for study document JSON helpers."""

from __future__ import annotations

import json

from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    content_for_persistence,
    render_sections_to_markdown,
    validate_section_id_coverage,
)

_SAMPLE = {
    "sections": [
        {
            "id": "mc_1",
            "heading": "Introduction",
            "content": "OOPS matters.",
            "code_blocks": [{"language": "python", "code": "x = 1"}],
            "subsections": [{"heading": "Why", "content": "Because."}],
        }
    ]
}


class TestStudyGenerationJson:
    def test_canonicalize_strips_fences_and_whitespace(self):
        raw = f"Here is JSON:\n```json\n{json.dumps(_SAMPLE)}\n```\nThanks."
        canonical = canonicalize_generation_json(raw)
        assert canonical.startswith('{"sections":')
        assert "```" not in canonical

    def test_render_sections_to_markdown(self):
        md = render_sections_to_markdown(_SAMPLE)
        assert "## Introduction" in md
        assert "OOPS matters." in md
        assert "```python" in md
        assert "### Why" in md

    def test_render_subsection_code_blocks_after_subsection_content(self):
        doc = {
            "sections": [
                {
                    "id": "ts_3",
                    "heading": "Inheritance",
                    "content": "Overview of inheritance.",
                    "subsections": [
                        {
                            "heading": "Single Inheritance",
                            "content": "One parent class.",
                            "code_blocks": [
                                {
                                    "language": "python",
                                    "code": "class Child(Parent):\n    pass",
                                    "explanation": "Single inheritance example.",
                                }
                            ],
                        },
                        {
                            "heading": "Multiple Inheritance",
                            "content": "Several parent classes.",
                        },
                    ],
                }
            ]
        }
        md = render_sections_to_markdown(doc)
        single_idx = md.index("### Single Inheritance")
        code_idx = md.index("```python")
        multiple_idx = md.index("### Multiple Inheritance")
        assert single_idx < code_idx < multiple_idx
        assert "Single inheritance example." in md

    def test_render_subsection_formula_blocks(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Derivatives",
                    "subsections": [
                        {
                            "heading": "Definition",
                            "content": "The derivative is defined as:",
                            "formula_blocks": [
                                {
                                    "notation": "LaTeX",
                                    "formula": "f'(x) = \\lim_{h \\to 0} \\frac{f(x+h)-f(x)}{h}",
                                    "explanation": "Limit definition.",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        md = render_sections_to_markdown(doc)
        assert "### Definition" in md
        assert "$$" in md
        assert "Limit definition." in md

    def test_render_formula_blocks_as_display_math(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Derivatives",
                    "content": "Definition below.",
                    "formula_blocks": [
                        {
                            "notation": "LaTeX",
                            "formula": "f'(x) = \\lim_{h \\to 0} \\frac{f(x + h) - f(x)}{h}",
                            "explanation": "Limit definition of the derivative.",
                        }
                    ],
                }
            ]
        }
        md = render_sections_to_markdown(doc)
        assert "## Derivatives" in md
        assert "$$" in md
        assert "f'(x)" in md
        assert "Limit definition of the derivative." in md

    def test_render_math_language_code_blocks_as_display_math(self):
        doc = {
            "sections": [
                {
                    "id": "ts_1",
                    "heading": "Limits",
                    "content": "Notation:",
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
        md = render_sections_to_markdown(doc)
        assert "$$" in md
        assert "lim x→a f(x) = L" in md
        assert "```math" not in md.lower()

    def test_render_strips_nested_code_fences_from_llm_output(self):
        doc = {
            "sections": [
                {
                    "id": "ts_2",
                    "heading": "Process Synchronization",
                    "content": "Peterson's algorithm.",
                    "formula_blocks": [
                        {
                            "notation": "Pseudo-code",
                            "formula": "```\nflag[0] = true;\nturn = 1;\n```",
                            "explanation": "Peterson step.",
                        }
                    ],
                    "code_blocks": [
                        {
                            "language": "Python",
                            "code": "```\nimport threading\nx = 1\n```",
                            "explanation": "Thread example.",
                        }
                    ],
                }
            ]
        }
        md = render_sections_to_markdown(doc)
        assert md.count("```") == 4  # one open + one close per block
        assert "flag[0] = true;" in md
        assert "import threading" in md
        assert "```\n```" not in md
        assert "Peterson step." in md
        assert "Thread example." in md

    def test_content_for_persistence_renders_json(self):
        persisted = content_for_persistence(json.dumps(_SAMPLE))
        assert "## Introduction" in persisted
        assert '"sections"' not in persisted

    def test_validate_section_id_coverage(self):
        checklist = [
            {"id": "mc_1", "priority": "required"},
            {"id": "mc_2", "priority": "required"},
        ]
        result = validate_section_id_coverage(_SAMPLE, checklist)
        assert result.missing_ids == {"mc_2"}
        assert result.coverage_ratio == 0.5

    def test_validate_section_id_coverage_uses_topic_split(self):
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_1",
                "priority": "required",
            },
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "priority": "required",
            },
        ]
        topic_split = [
            {"id": "ts_1", "heading": "Intro", "depth": "brief"},
            {"id": "ts_2", "heading": "Basics", "depth": "medium"},
        ]
        doc = {"sections": [{"id": "ts_1", "heading": "Intro", "content": "x"}]}
        result = validate_section_id_coverage(doc, checklist, topic_split=topic_split)
        assert result.missing_ids == {"ts_2"}
        assert result.coverage_ratio == 0.5

    def test_render_vague_improve_response(self):
        doc = {
            "improve_status": "vague",
            "message": "IMPROVE STATUS: Feedback too vague to apply.",
        }
        md = render_sections_to_markdown(doc)
        assert "IMPROVE STATUS" in md

    def test_parse_vague_regenerate_response(self):
        from src.api.utils.study_agent_utils.generation.study_generation_json import (
            is_vague_regenerate_response,
            parse_generation_document,
        )

        raw = '{"regenerate_status":"vague","message":"too vague"}'
        doc = parse_generation_document(raw)
        assert doc is not None
        assert is_vague_regenerate_response(doc)

    def test_format_must_cover_checklist_line_uses_canonical_section_id(self):
        with_section = format_must_cover_checklist_line(
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Limits",
                "requirement": "Define limits",
                "priority": "required",
                "depth_gate": "worked example",
            }
        )
        assert "mc_2 (section_id: ts_2): Limits" in with_section
        assert "depth_gate: worked example" in with_section

        legacy = format_must_cover_checklist_line(
            {
                "id": "mc_2",
                "concept": "Encapsulation",
                "requirement": "Define encapsulation",
                "priority": "required",
            }
        )
        assert "mc_2 (section_id: mc_2): Encapsulation" in legacy
