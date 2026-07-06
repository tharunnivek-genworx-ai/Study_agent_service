# tests/test_section_block_relocate_prompt.py
"""Smoke tests for placement-only block relocate prompt builder."""

from __future__ import annotations

from src.api.control.study_agent.nodes.study_agent_node import (
    _build_section_patch_messages,
    _uses_placement_relocate_prompt,
)
from src.api.control.study_agent.prompts.section import (
    section_block_relocate_prompt,
    section_rework_prompt,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
)

_SAMPLE_DOC = {
    "sections": [
        {
            "id": "ts_2",
            "heading": "Derivatives",
            "content": "The derivative f'(x) = lim(h→0) ...",
            "formula_blocks": [],
        }
    ]
}

_SECTION_FAILURES = [
    {
        "section_id": "ts_2",
        "heading": "Derivatives",
        "failures": [
            {
                "category": "document_coherence",
                "check_id": "det_equation_in_content",
                "evidence": "Section 'Derivatives': Prose contains display-math patterns",
                "corrective_hint": "Move equations to formula_blocks.",
            }
        ],
    }
]

_RELOCATION_PLANS = [
    {
        "check_id": "det_equation_in_content",
        "section_id": "ts_2",
        "relocations": [
            {
                "action": "extract",
                "confidence": "low",
                "section_id": "ts_2",
                "span_text": "f'(x) = lim(h→0) ...",
            }
        ],
        "has_low_confidence": True,
    }
]


class TestSectionBlockRelocatePrompt:
    def test_user_message_includes_relocation_plan_not_scoped_checklist(self):
        msg = section_block_relocate_prompt.build_user_message(
            topic_title="Calculus",
            teaching_instruction="Explain for beginners.",
            document_outline=build_document_outline(_SAMPLE_DOC),
            section_failures=_SECTION_FAILURES,
            document=_SAMPLE_DOC,
            relocation_plans=_RELOCATION_PLANS,
            domain="STEM",
        )
        assert "<relocation_plan>" in msg
        assert "relocation_plans" in msg
        assert "<sections_to_fix>" in msg
        assert "<scoped_must_cover_checklist>" not in msg
        assert "Change only block fields" in msg

    def test_system_prompt_excludes_substance_and_failure_remediation_blocks(self):
        relocate_system = section_block_relocate_prompt.build_system_prompt(
            has_reference=False,
            domain="STEM",
        )
        rework_system = section_rework_prompt.build_system_prompt(
            has_reference=False,
            domain="STEM",
        )
        assert "RELOCATION RULES" in relocate_system
        assert "SUBSTANCE RULES" not in relocate_system
        assert "FAILURE REMEDIATION" not in relocate_system
        assert "Thin coverage" not in relocate_system
        assert "SUBSTANCE RULES" in rework_system
        assert "FAILURE REMEDIATION" in rework_system

    def test_stem_domain_uses_formula_only_patch_schema(self):
        system = section_block_relocate_prompt.build_system_prompt(
            has_reference=False,
            domain="STEM",
        )
        assert '"formula_blocks":' in system
        assert '"code_blocks":' not in system

    def test_placement_only_uses_relocate_prompt_without_relocation_plans(self):
        state = {
            "qc_failure_class": "placement_only",
            "qc_relocation_plans": None,
            "node_title": "Calculus",
            "effective_instruction": "Explain clearly.",
            "domain": "STEM",
            "qc_section_failures": _SECTION_FAILURES,
        }
        assert _uses_placement_relocate_prompt(state) is True

        system, user = _build_section_patch_messages(state, _SAMPLE_DOC)
        assert "RELOCATION RULES" in system
        assert "SUBSTANCE RULES" not in system
        assert "<sections_to_fix>" in user
