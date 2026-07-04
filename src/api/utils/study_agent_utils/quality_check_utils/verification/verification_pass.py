"""Unified Groq QC verification passes (full document vs targeted retry).

Wrappers around ``run_llm_verification_pass`` with study-specific prompts:

  - ``run_verification_pass`` — pass 1 full QC; receives hash-gated frozen ids
  - ``run_retry_verification_pass`` — pass 2 targeted QC on ``fixed_sections`` only

Frozen checklist/section ids are filtered upstream in ``quality_check_node`` via
``resolve_frozen_for_full_qc`` before calling full verification.
"""

from __future__ import annotations

from typing import Any

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.qc import (
    qc_retry_verification_prompt,
    qc_verification_prompt,
)
from src.api.utils.LLM_utils.groq_qc_client import call_groq_qc_verification
from src.api.utils.study_agent_utils.quality_check_utils.verification.llm_verification import (
    run_llm_verification_pass,
)


async def run_verification_pass(
    *,
    topic_title: str,
    teaching_instruction: str,
    generated_content: str,
    must_cover_checklist: list[dict[str, Any]],
    frozen_check_ids: list[str] | None,
    frozen_section_ids: list[str] | None,
    topic_split: list[dict[str, Any]] | None = None,
    domain: str = "",
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Single Groq pass over the full study document."""
    verification, meta = await run_llm_verification_pass(
        build_user_message=qc_verification_prompt.build_user_message,
        system_prompt=qc_verification_prompt.build_system_prompt(domain=domain),
        reprompt_system=qc_verification_prompt.REPROMPT_SYSTEM,
        call_llm=call_groq_qc_verification,
        graph_node="qc_verification",
        model_setting=llm_settings.qc_llm_model,
        user_message_kwargs={
            "topic_title": topic_title,
            "teaching_instruction": teaching_instruction,
            "generated_content": generated_content,
            "must_cover_checklist": must_cover_checklist,
            "frozen_check_ids": frozen_check_ids,
            "frozen_section_ids": frozen_section_ids,
            "topic_split": topic_split,
            "domain": domain,
            "max_doc_chars": llm_settings.qc_document_max_chars,
        },
        pass_label="QC verification",
    )
    meta["verification_mode"] = "full"
    return verification, meta


async def run_retry_verification_pass(
    *,
    teaching_instruction: str,
    document_outline: str,
    revised_sections: list[dict[str, Any]],
    section_failures: list[dict[str, Any]],
    must_cover_checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
    domain: str = "",
    prior_teaching_alignment_failure: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Targeted Groq pass over patched or inserted sections only."""
    verification, meta = await run_llm_verification_pass(
        build_user_message=qc_retry_verification_prompt.build_user_message,
        system_prompt=qc_retry_verification_prompt.build_system_prompt(domain=domain),
        reprompt_system=qc_retry_verification_prompt.REPROMPT_SYSTEM,
        call_llm=call_groq_qc_verification,
        graph_node="qc_retry_verification",
        model_setting=llm_settings.qc_llm_model,
        user_message_kwargs={
            "teaching_instruction": teaching_instruction,
            "document_outline": document_outline,
            "revised_sections": revised_sections,
            "section_failures": section_failures,
            "must_cover_checklist": must_cover_checklist,
            "topic_split": topic_split,
            "domain": domain,
            "prior_teaching_alignment_failure": prior_teaching_alignment_failure,
        },
        pass_label="QC targeted verification",
    )
    meta["verification_mode"] = "targeted"
    return verification, meta
