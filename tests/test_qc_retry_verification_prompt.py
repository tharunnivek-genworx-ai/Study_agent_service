# tests/test_qc_retry_verification_prompt.py
"""Smoke tests for targeted QC retry verification prompt builder."""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.qc import qc_retry_verification_prompt

_REVISED_SECTIONS = [
    {
        "id": "mc_2",
        "heading": "Encapsulation",
        "content": "Encapsulation hides internal state.",
        "code_blocks": [{"language": "python", "code": "class A:\n    pass"}],
    }
]

_SECTION_FAILURES = [
    {
        "section_id": "mc_2",
        "heading": "Encapsulation",
        "failures": [
            {
                "category": "content_accuracy",
                "evidence": "Old wrong claim.",
                "corrective_hint": "Explain encapsulation correctly.",
            }
        ],
    }
]

_CHECKLIST = [
    {
        "id": "mc_2",
        "concept": "Encapsulation",
        "requirement": "Define encapsulation",
        "priority": "required",
    }
]


class TestQcRetryVerificationPrompt:
    def test_user_message_scoped_to_revised_sections(self):
        msg = qc_retry_verification_prompt.build_user_message(
            teaching_instruction="Explain for beginners.",
            document_outline="- [mc_1] Intro\n- [mc_2] Encapsulation",
            revised_sections=_REVISED_SECTIONS,
            section_failures=_SECTION_FAILURES,
            must_cover_checklist=_CHECKLIST,
        )
        assert "<revised_sections_json>" in msg
        assert "<previously_failed>" in msg
        assert "<document_outline>" in msg
        assert "<document_context>" not in msg
        assert "mc_2" in msg
        assert "Old wrong claim." in msg
        parsed = json.loads(
            msg.split("<revised_sections_json>")[1]
            .split("</revised_sections_json>")[0]
            .strip()
        )
        assert len(parsed["sections"]) == 1

    def test_system_prompt_includes_retry_recommendation(self):
        system = qc_retry_verification_prompt.SYSTEM_PROMPT
        assert "retry_recommendation" in system
        assert "TARGETED" in system
        assert "revised_sections_json" in system

    def test_system_prompt_uses_document_outline_not_context(self):
        system = qc_retry_verification_prompt.SYSTEM_PROMPT
        assert "document_coherence" in system
        assert "document_outline" in system
        assert "document_context" not in system

    def test_user_message_does_not_include_document_context(self):
        msg = qc_retry_verification_prompt.build_user_message(
            teaching_instruction="Explain for beginners.",
            document_outline="- [mc_1] Intro\n- [mc_2] Encapsulation",
            revised_sections=_REVISED_SECTIONS,
            section_failures=_SECTION_FAILURES,
            must_cover_checklist=_CHECKLIST,
        )
        assert "<document_outline>" in msg
        assert "<document_context>" not in msg
        assert "root-cause-fixed" in msg

    def test_system_prompt_includes_must_cover_hygiene_rules(self):
        system = qc_retry_verification_prompt.SYSTEM_PROMPT
        assert "checklist_id exactly" in system
        assert "corrective_hint empty when passed=true" in system
        assert "only states the final formula, rule, or result" in system

    def test_user_message_includes_section_id_on_checklist_lines(self):
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Encapsulation",
                "requirement": "Define encapsulation",
                "priority": "required",
            }
        ]
        msg = qc_retry_verification_prompt.build_user_message(
            teaching_instruction="Explain for beginners.",
            document_outline="- [ts_2] Encapsulation",
            revised_sections=_REVISED_SECTIONS,
            section_failures=_SECTION_FAILURES,
            must_cover_checklist=checklist,
        )
        checklist_block = msg.split("<must_cover_checklist>")[1].split(
            "</must_cover_checklist>"
        )[0]
        assert "mc_2 (section_id: ts_2)" in checklist_block
