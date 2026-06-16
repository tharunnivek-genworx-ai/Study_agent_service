"""Generate, regenerate, or improve study material using Groq."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config.dbconfig import settings
from src.api.control.prompts.study_agent_prompts import (
    generation_prompt,
    improve_prompt,
    regeneration_prompt,
)
from src.api.core.agents.study_material.state import StudyMaterialGraphState
from src.api.utils.groq_retry import invoke_llm_rotating

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
            user_message,
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
            user_message,
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
        user_message,
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
