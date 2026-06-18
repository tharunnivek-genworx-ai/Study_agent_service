# src/api/control/study_agent/nodes/study_agent_node.py
"""Generate, regenerate, or improve study material using Groq."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config.dbconfig import settings
from src.api.control.study_agent.prompts import (
    generation_prompt,
    improve_prompt,
    regeneration_prompt,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.LLM_utils.groq_retry import invoke_llm_rotating

logger = logging.getLogger(__name__)

_DEFAULT_INSTRUCTION = (
    "No specific teaching instruction provided. Write for a new IT hire "
    "who knows basic programming but is unfamiliar with the topic."
)

_NO_REFERENCE_PLACEHOLDER = "no reference material provided."


def _teaching_instruction(state: StudyMaterialGraphState) -> str:
    return state.get("effective_instruction") or _DEFAULT_INSTRUCTION


def _has_reference_material(state: StudyMaterialGraphState) -> bool:
    """True when meaningful reference text is available for this run."""
    text = (state.get("extracted_reference_text") or "").strip()
    if not text or text.lower() == _NO_REFERENCE_PLACEHOLDER:
        return False
    return bool(
        state.get("has_reference_material")
        or state.get("reference_material_id") is not None
    )


def _reference_text(state: StudyMaterialGraphState) -> str:
    return (state.get("extracted_reference_text") or "").strip()


def _build_qc_feedback_block(state: StudyMaterialGraphState) -> str:
    """Build QC feedback + reference material block for retry attempts.

    Only returns content when qc_attempt > 0 (i.e. this is a retry after QC failure).
    When reference material exists, it is re-included so the writer can correct
    against the source.
    """
    qc_attempt = state.get("qc_attempt") or 0
    if qc_attempt == 0:
        return ""

    qc_feedback = (state.get("qc_feedback") or "").strip()
    if not qc_feedback:
        return ""

    parts: list[str] = [
        "\n<quality_check_feedback>",
        "IMPORTANT: Your previous output failed quality evaluation. "
        "You MUST address ALL issues listed below in this revision.",
        "",
        qc_feedback,
        "</quality_check_feedback>",
    ]

    # Re-include reference material for reference-based retries
    has_reference = _has_reference_material(state)
    if has_reference:
        ref_text = _reference_text(state)
        if ref_text:
            parts.append("\n<reference_material_for_correction>")
            parts.append(ref_text)
            parts.append("</reference_material_for_correction>")

    return "\n".join(parts)


def _build_previous_failed_qc_feedback_block(state: StudyMaterialGraphState) -> str:
    """Build a prompt block for the previously failed QC feedback from database.

    Only applies to regenerate/improve mode runs when starting from a draft
    that failed QC.
    """
    failed_feedback = state.get("failed_qc_feedback")
    if not failed_feedback:
        return ""

    return (
        "\n<previous_failed_quality_check_feedback>\n"
        "IMPORTANT: The draft you are editing failed a previous quality evaluation. "
        "Make sure to address the following issues in your new output:\n\n"
        f"{failed_feedback.strip()}\n"
        "</previous_failed_quality_check_feedback>"
    )


def _build_user_message(state: StudyMaterialGraphState) -> tuple[str, str]:
    mode = state.get("generation_mode") or "generate"
    teaching_instruction = _teaching_instruction(state)
    has_reference = _has_reference_material(state)
    reference_text = _reference_text(state) if has_reference else ""

    if mode == "regenerate":
        goal = (state.get("mentor_feedback") or "").strip()
        if not goal:
            goal = "Produce a meaningfully improved rewrite addressing gaps in the prior draft."
        user_message = regeneration_prompt.USER_MESSAGE_TEMPLATE.format(
            topic_title=state.get("node_title", ""),
            teaching_instruction_text=teaching_instruction,
            mentor_regeneration_goal=goal,
            current_draft_content=state.get("current_draft_content") or "",
            reference_block=regeneration_prompt.format_reference_user_block(
                reference_text, has_reference=has_reference
            ),
        )
        return (
            regeneration_prompt.build_system_prompt(has_reference=has_reference),
            user_message
            + _build_previous_failed_qc_feedback_block(state)
            + _build_qc_feedback_block(state),
        )

    if mode == "improve":
        user_message = improve_prompt.USER_MESSAGE_TEMPLATE.format(
            topic_title=state.get("node_title", ""),
            teaching_instruction_text=teaching_instruction,
            mentor_feedback_text=state.get("mentor_feedback") or "",
            current_draft_content=state.get("current_draft_content") or "",
            reference_block=improve_prompt.format_reference_user_block(
                reference_text, has_reference=has_reference
            ),
        )
        return (
            improve_prompt.build_system_prompt(has_reference=has_reference),
            user_message
            + _build_previous_failed_qc_feedback_block(state)
            + _build_qc_feedback_block(state),
        )

    user_message = generation_prompt.USER_MESSAGE_TEMPLATE.format(
        topic_title=state.get("node_title", ""),
        teaching_instruction_text=teaching_instruction,
        reference_block=generation_prompt.format_reference_user_block(
            reference_text, has_reference=has_reference
        ),
    )
    return (
        generation_prompt.build_system_prompt(has_reference=has_reference),
        user_message + _build_qc_feedback_block(state),
    )


async def study_agent_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    api_keys_configured = any(
        [
            settings.groq_api_key,
            settings.groq_api_key_2,
            settings.groq_api_key_3,
            settings.groq_api_key_4,
        ]
    )
    if not api_keys_configured:
        return {"error": "No GROQ API keys are configured."}

    system_prompt, user_message = _build_user_message(state)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"

    try:
        content, llm_model_used, token_usage = await invoke_llm_rotating(
            messages=messages,
            model=settings.llm_model,
            temperature=0.3,
            timeout=120,
        )
    except Exception as exc:
        logger.exception("Groq study material generation failed")
        return {"error": f"Study material generation failed: {exc}"}

    raw_content = str(content).strip()
    cleaned_content = raw_content
    if cleaned_content.startswith("---"):
        cleaned_content = cleaned_content[3:].strip()

    improve_status = None
    regenerate_status = None

    mode = state.get("generation_mode") or "generate"
    if mode == "improve":
        if cleaned_content.startswith("IMPROVE STATUS:"):
            improve_status = "vague"
        else:
            improve_status = "generated"
    elif mode == "regenerate":
        if cleaned_content.startswith("REGENERATE STATUS:"):
            regenerate_status = "vague"
        else:
            regenerate_status = "generated"

    return {
        "generated_content": str(content),
        "prompt_snapshot": prompt_snapshot,
        "token_usage": token_usage,
        "llm_model_used": llm_model_used,
        "improve_status": improve_status,
        "regenerate_status": regenerate_status,
        "llm_output_content": str(content),
    }
