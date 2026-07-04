"""Minimal graph-state dict for prompt test retries."""

from __future__ import annotations

from typing import Any

from test_new_prompts.runners._types import ChecklistRunResult, PromptTestInputs


def make_pipeline_state(
    *,
    inputs: PromptTestInputs,
    checklist: ChecklistRunResult,
    generated_content: str = "",
    generation_mode: str = "generate",
    **extra: Any,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "node_title": inputs.topic,
        "effective_instruction": inputs.effective_instruction,
        "generation_mode": generation_mode,
        "has_reference_material": False,
        "extracted_reference_text": "",
        "domain": checklist.domain,
        "topic_split": list(checklist.topic_split),
        "must_cover_checklist": list(checklist.must_cover_checklist),
        "generated_content": generated_content,
        "qc_retry_mode": "none",
        "qc_reverify_section_ids": [],
        "qc_missing_checklist_ids": [],
        "qc_section_failures": [],
        "qc_attempt": 0,
        "qc_feedback": "",
        "qc_passed": False,
        "qc_result": None,
        "qc_frozen_check_ids": [],
        "qc_frozen_section_keys": [],
        "qc_section_content_hashes": {},
        "fixed_sections": None,
    }
    state.update(extra)
    return state
