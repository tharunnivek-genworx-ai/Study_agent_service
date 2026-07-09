# tests/test_section_rework_prompt.py
"""Smoke tests for section rework prompt builder."""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.section import section_rework_prompt
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
)

_SAMPLE_DOC = {
    "sections": [
        {"id": "mc_1", "heading": "Intro", "content": "Overview."},
        {
            "id": "mc_2",
            "heading": "Encapsulation",
            "content": "Wrong claim here.",
            "code_blocks": [{"language": "python", "code": "x = 1"}],
        },
    ]
}

_SECTION_FAILURES = [
    {
        "section_id": "mc_2",
        "heading": "Encapsulation",
        "failures": [
            {
                "category": "content_accuracy",
                "evidence": "Wrong claim here.",
                "corrective_hint": "Fix the technical claim.",
            }
        ],
    }
]


class TestSectionReworkPrompt:
    def test_user_message_includes_outline_and_sections_to_fix_not_full_document(self):
        msg = section_rework_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=_SECTION_FAILURES,
            document=_SAMPLE_DOC,
        )
        assert "<topic>OOPS</topic>" in msg
        assert "<document_outline>" in msg
        assert "<document_context>" not in msg
        assert "<sections_to_fix>" in msg
        assert "mc_2" in msg
        assert "Wrong claim here." in msg
        assert "Fix the technical claim." in msg
        assert '"sections": [' not in msg.split("<sections_to_fix>")[0]

    def test_system_prompt_requires_sections_only_output(self):
        system = section_rework_prompt.build_system_prompt(has_reference=False)
        assert '"sections"' in system
        assert "sections_to_fix" in system
        assert "document_context" not in system
        assert "PATCH SCOPE" in system
        assert (
            "Every subsection, code_block, and formula_block not named by a failure's evidence"
            in system
        )

    def test_user_message_closing_enforces_patch_scope(self):
        msg = section_rework_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=_SECTION_FAILURES,
            document=_SAMPLE_DOC,
        )
        assert (
            "change only what each failure's evidence or corrective_hint names" in msg
        )
        assert "every other subsection" in msg
        assert "exactly as given in current_section_json" in msg

    def test_stem_domain_includes_stem_rules_only(self):
        system = section_rework_prompt.build_system_prompt(
            has_reference=False, domain="STEM"
        )
        assert (
            "NO CODE, EVER: this section's output schema has no code_blocks field"
            in system
        )
        assert "Programming: code must be syntactically valid" not in system
        assert "Conceptual: named facts must be accurate" not in system

    def test_sections_to_fix_includes_current_section_json(self):
        msg = section_rework_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=_SECTION_FAILURES,
            document=_SAMPLE_DOC,
        )
        block = msg.split("<sections_to_fix>")[1].split("</sections_to_fix>")[0]
        parsed = json.loads(block.strip())
        entry = parsed["sections_to_fix"][0]
        assert entry["id"] == "mc_2"
        assert entry["current_section_json"]["heading"] == "Encapsulation"

    def test_user_message_includes_scoped_checklist_for_patch_sections(self):
        checklist = [
            {
                "id": "mc_2",
                "concept": "Encapsulation",
                "requirement": "Explain with a worked example.",
                "priority": "required",
                "depth_gate": "definition + mechanism + example",
            },
            {
                "id": "mc_3",
                "concept": "Inheritance",
                "requirement": "Cover parent/child relationship.",
                "priority": "required",
            },
        ]
        msg = section_rework_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=_SECTION_FAILURES,
            document=_SAMPLE_DOC,
            must_cover_checklist=checklist,
            patch_section_ids=["mc_2"],
        )
        assert "<scoped_must_cover_checklist>" in msg
        assert "mc_2 (section_id: mc_2)" in msg
        assert "depth_gate: definition + mechanism + example" in msg
        assert (
            "mc_3"
            not in msg.split("<scoped_must_cover_checklist>")[1].split(
                "</scoped_must_cover_checklist>"
            )[0]
        )
        assert "Satisfy every depth_gate component for scoped checklist items" in msg

    def test_scoped_checklist_matches_topic_split_section_ids(self):
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Encapsulation",
                "requirement": "Explain with a worked example.",
                "priority": "required",
                "depth_gate": "definition + mechanism + example",
            },
            {
                "id": "mc_3",
                "section_id": "ts_3",
                "concept": "Inheritance",
                "requirement": "Cover parent/child relationship.",
                "priority": "required",
            },
        ]
        msg = section_rework_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=[
                {
                    "section_id": "ts_2",
                    "heading": "Encapsulation",
                    "failures": [
                        {
                            "category": "must_cover",
                            "evidence": "Thin coverage.",
                            "corrective_hint": "Add depth.",
                        }
                    ],
                }
            ],
            document=_SAMPLE_DOC,
            must_cover_checklist=checklist,
            patch_section_ids=["ts_2"],
        )
        scoped_block = msg.split("<scoped_must_cover_checklist>")[1].split(
            "</scoped_must_cover_checklist>"
        )[0]
        assert "mc_2 (section_id: ts_2)" in scoped_block
        assert "mc_3" not in scoped_block

    def test_system_prompt_includes_subsection_formula_blocks(self):
        system = section_rework_prompt.build_system_prompt(has_reference=False)
        assert '"formula_blocks"' in system
        assert "subsection" in system
        assert "no equations inside this field" in system

    def test_subsection_equation_failure_adds_remediation_block(self):
        section_failures = [
            {
                "section_id": "ts_2",
                "heading": "Differentiation Rules",
                "failures": [
                    {
                        "category": "document_coherence",
                        "evidence": (
                            "Section 'Differentiation Rules', subsection "
                            "'Examples of Differentiation Rules': Prose contains "
                            "display-math patterns"
                        ),
                        "corrective_hint": (
                            "Move equations and derivation steps from content into "
                            "formula_blocks with non-empty explanation fields."
                        ),
                    }
                ],
            }
        ]
        msg = section_rework_prompt.build_user_message(
            topic_title="Calculus",
            teaching_instruction="Teach at depth.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=section_failures,
            document=_SAMPLE_DOC,
        )
        assert "<subsection_equation_remediation>" in msg
        assert "subsection 'Examples of Differentiation Rules'" in msg or (
            "Examples of Differentiation Rules" in msg
        )
        assert "prose-only" in msg
        block = msg.split("<sections_to_fix>")[1].split("</sections_to_fix>")[0]
        parsed = json.loads(block.strip())
        entry = parsed["sections_to_fix"][0]
        assert entry["subsections_to_fix"][0]["heading"] == (
            "Examples of Differentiation Rules"
        )
