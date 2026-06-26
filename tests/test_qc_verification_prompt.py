# tests/test_qc_verification_prompt.py
"""Smoke tests for unified QC verification prompt builder."""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.qc import qc_verification_prompt
from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    extract_structure,
)

_SAMPLE_DOC = json.dumps(
    {
        "sections": [
            {"id": "mc_1", "heading": "Introduction", "content": "OOPS is important."},
            {
                "id": "mc_encap",
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
                        "explanation": "Demonstrates private balance via underscore naming.",
                    }
                ],
            },
        ]
    }
)

_CHECKLIST = [
    {
        "id": "mc_1",
        "concept": "Encapsulation",
        "requirement": "Define encapsulation",
        "priority": "required",
        "depth_gate": "Concept defined with a concrete example.",
    },
    {
        "id": "mc_2",
        "concept": "Inheritance",
        "requirement": "Explain inheritance",
        "priority": "recommended",
    },
]


class TestVerificationPrompt:
    def test_user_message_includes_topic_split_when_provided(self):
        topic_split = [
            {
                "id": "ts_1",
                "heading": "Intro",
                "purpose": "overview",
            }
        ]
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            topic_split=topic_split,
        )
        assert "<topic_split>" in msg
        assert "ts_1" in msg
        assert "Intro" in msg

    def test_user_message_includes_domain_when_provided(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            domain="Programming",
        )
        assert "<domain>Programming</domain>" in msg

    def test_user_message_includes_document_with_inline_code(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            must_cover_checklist=_CHECKLIST,
        )
        assert "<topic>OOPS</topic>" in msg
        assert "<must_cover_checklist>" in msg
        assert "depth_gate:" in msg
        assert "<study_document_json>" in msg
        assert "Encapsulation hides details." in msg
        assert "BankAccount" in msg
        assert "<code_review_units>" not in msg

    def test_system_prompt_covers_all_six_categories(self):
        system = qc_verification_prompt.SYSTEM_PROMPT
        assert "must_cover" in system
        assert "content_accuracy" in system
        assert "teaching_alignment" in system
        assert "document_coherence" in system
        assert "code_quality" in system
        assert "stack_fidelity" in system
        assert "code_artifact_id" in system
        assert "section_id" in system
        assert "ANTI-INFLATION RULES" in system

    def test_system_prompt_includes_depth_gate_procedure(self):
        system = qc_verification_prompt.SYSTEM_PROMPT
        assert "depth_gate" in system
        assert "explanation" in system

    def test_system_prompt_includes_retry_recommendation(self):
        system = qc_verification_prompt.SYSTEM_PROMPT
        assert "retry_recommendation" in system
        assert "section_patch" in system
        assert "section_insert" in system
        assert "full_regeneration" in system

    def test_frozen_check_ids_excluded_from_checklist(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            must_cover_checklist=_CHECKLIST,
            frozen_check_ids=["mc_1"],
        )
        checklist_block = msg.split("<must_cover_checklist>")[1].split(
            "</must_cover_checklist>"
        )[0]
        assert "mc_1" not in checklist_block
        assert "mc_2" in checklist_block

    def test_frozen_section_ids_listed_for_skip(self):
        structure = extract_structure(_SAMPLE_DOC)
        section_id = structure.code_artifacts[0].section_id
        assert section_id
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            frozen_section_ids=[section_id],
        )
        assert "<frozen_section_ids>" in msg
        assert section_id in msg
        assert "<code_review_units>" not in msg

    def test_empty_document_still_includes_study_document(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
        )
        assert "<study_document_json>" in msg
        assert "Encapsulation hides details." in msg

    def test_closing_instruction_requests_full_json_report(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
        )
        assert "Return the complete JSON report" in msg
        assert "depth_gate" in msg
        assert "trace the actual output" in msg

    def test_teaching_instruction_included(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Focus on Python 3.12 only.",
            generated_content=_SAMPLE_DOC,
        )
        assert "<teaching_instruction>" in msg
        assert "Focus on Python 3.12 only." in msg

    def test_recommended_items_remain_in_checklist_block(self):
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            must_cover_checklist=_CHECKLIST,
        )
        assert "[recommended] mc_2" in msg
        assert "[required] mc_1" in msg

    def test_study_document_is_canonical_json(self):
        fenced = f"```json\n{_SAMPLE_DOC}\n```"
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=fenced,
        )
        study_block = msg.split("<study_document_json>")[1].split(
            "</study_document_json>"
        )[0]
        assert "```" not in study_block
        parsed = json.loads(study_block.strip())
        assert "sections" in parsed

    def test_system_prompt_requires_json_only_output(self):
        system = qc_verification_prompt.SYSTEM_PROMPT
        assert "Return ONLY valid JSON" in system
        assert "Start with {" in system

    def test_system_prompt_includes_accuracy_hygiene_rules(self):
        system = qc_verification_prompt.SYSTEM_PROMPT
        assert "only states the final formula, rule, or result" in system
        assert "NEVER set corrective_hint when passed=true" in system
        assert "retry_recommendation.mode" in system

    def test_user_message_includes_section_id_on_checklist_lines(self):
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_1",
                "concept": "Encapsulation",
                "requirement": "Define encapsulation",
                "priority": "required",
            }
        ]
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            must_cover_checklist=checklist,
        )
        checklist_block = msg.split("<must_cover_checklist>")[1].split(
            "</must_cover_checklist>"
        )[0]
        assert "mc_1 (section_id: ts_1)" in checklist_block

    def test_frozen_filters_apply_to_checklist_and_section_ids(self):
        structure = extract_structure(_SAMPLE_DOC)
        section_id = structure.code_artifacts[0].section_id
        msg = qc_verification_prompt.build_user_message(
            topic_title="OOPS",
            teaching_instruction="Explain for beginners.",
            generated_content=_SAMPLE_DOC,
            must_cover_checklist=_CHECKLIST,
            frozen_check_ids=["mc_1"],
            frozen_section_ids=[section_id],
        )
        checklist_block = msg.split("<must_cover_checklist>")[1].split(
            "</must_cover_checklist>"
        )[0]
        frozen_block = msg.split("<frozen_section_ids>")[1].split(
            "</frozen_section_ids>"
        )[0]
        assert "mc_1" not in checklist_block
        assert section_id in frozen_block
        assert "mc_2" in checklist_block
