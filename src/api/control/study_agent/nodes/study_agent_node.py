# src/api/control/study_agent/nodes/study_agent_node.py
"""Generate, regenerate, or improve study material using Groq Llama 70B."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config.llm_config import llm_settings
from src.api.control.study_agent.prompts.generation import (
    generation_prompt,
    improve_prompt,
    regeneration_prompt,
)
from src.api.control.study_agent.prompts.section import (
    section_insert_prompt,
    section_rework_prompt,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    is_reference_required_response,
    parse_generation_document,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
    merge_full_regeneration_preserving_passing,
)

logger = logging.getLogger(__name__)


def _build_user_message(state: StudyMaterialGraphState) -> tuple[str, str]:
    """Return system prompt and user message for a JSON study document response."""
    retry_mode = helpers.qc_retry_mode(state)
    mode = state.get("generation_mode") or "generate"
    teaching_instruction = helpers.teaching_instruction(state)
    has_reference = helpers.has_reference_material(state)
    reference_text = helpers.reference_text(state) if has_reference else ""
    reference_block = helpers.format_reference_block(has_reference, reference_text)

    must_cover_block = helpers.build_must_cover_block(state)
    topic_split_block = helpers.build_topic_split_block(state)
    domain_block = helpers.build_domain_block(state)
    qc_block = helpers.build_qc_feedback_block(state)
    previous_failed_qc_block = helpers.build_previous_failed_qc_feedback_block(state)

    if retry_mode == "full_regeneration" or mode == "generate":
        user_message = generation_prompt.build_user_message(
            topic_title=state.get("node_title", ""),
            teaching_instruction_text=teaching_instruction,
            must_cover_block=must_cover_block,
            topic_split_block=topic_split_block,
            domain_block=domain_block,
            reference_block=reference_block,
            qc_fix_block=qc_block,
        )
        return (
            generation_prompt.build_system_prompt(
                has_reference=has_reference,
                domain=state.get("domain"),
            ),
            user_message,
        )

    if mode == "regenerate":
        goal = (state.get("mentor_feedback") or "").strip()
        if not goal:
            goal = "Produce a meaningfully improved rewrite addressing gaps in the prior draft."
        user_message = regeneration_prompt.build_user_message(
            topic_title=state.get("node_title", ""),
            teaching_instruction_text=teaching_instruction,
            mentor_regeneration_goal=goal,
            current_draft_content=state.get("current_draft_content") or "",
            reference_block=reference_block,
            must_cover_block=must_cover_block,
            topic_split_block=topic_split_block,
            domain_block=domain_block,
            previous_failed_qc_block=previous_failed_qc_block,
            qc_fix_block=qc_block,
        )
        return (
            regeneration_prompt.build_system_prompt(
                has_reference=has_reference,
                domain=state.get("domain"),
            ),
            user_message,
        )

    user_message = improve_prompt.build_user_message(
        topic_title=state.get("node_title", ""),
        teaching_instruction_text=teaching_instruction,
        mentor_feedback_text=state.get("mentor_feedback") or "",
        current_draft_content=state.get("current_draft_content") or "",
        reference_block=reference_block,
        must_cover_block=must_cover_block,
        topic_split_block=topic_split_block,
        domain_block=domain_block,
        previous_failed_qc_block=previous_failed_qc_block,
        qc_fix_block=qc_block,
    )
    return (
        improve_prompt.build_system_prompt(
            has_reference=has_reference,
            domain=state.get("domain"),
        ),
        user_message,
    )


def _build_section_patch_messages(
    state: StudyMaterialGraphState,
    document: dict[str, Any],
) -> tuple[str, str]:
    has_reference = helpers.has_reference_material(state)
    reference_block = section_rework_prompt.format_reference_block(
        helpers.reference_text(state),
        has_reference=has_reference,
    )
    section_failures = state.get("qc_section_failures") or []
    patch_section_ids = helpers.section_ids_from_failures(section_failures)
    user_message = section_rework_prompt.build_user_message(
        topic_title=state.get("node_title", ""),
        teaching_instruction=helpers.teaching_instruction(state),
        document_outline=build_document_outline(document),
        section_failures=section_failures,
        document=document,
        domain=state.get("domain") or "",
        topic_split_block=helpers.build_scoped_topic_split_block(
            state,
            section_ids=patch_section_ids,
        ),
        reference_block=reference_block,
        must_cover_checklist=state.get("must_cover_checklist") or [],
        patch_section_ids=patch_section_ids,
    )
    return (
        section_rework_prompt.build_system_prompt(
            has_reference=has_reference,
            domain=state.get("domain"),
        ),
        user_message,
    )


def _build_section_insert_messages(
    state: StudyMaterialGraphState,
    document: dict[str, Any],
) -> tuple[str, str]:
    missing_ids = set(state.get("qc_missing_checklist_ids") or [])
    checklist = state.get("must_cover_checklist") or []
    topic_split = state.get("topic_split") or []
    topic_split_by_id = {
        str(entry.get("id", "")).strip(): entry
        for entry in topic_split
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    }

    missing_items = [item for item in checklist if item.get("id") in missing_ids]
    for missing_id in sorted(missing_ids):
        if any(item.get("id") == missing_id for item in missing_items):
            continue
        entry = topic_split_by_id.get(missing_id)
        if entry is None:
            continue
        missing_items.append(
            {
                "id": missing_id,
                "section_id": missing_id,
                "concept": str(entry.get("heading") or missing_id),
                "requirement": str(
                    entry.get("purpose") or entry.get("coverage_notes") or ""
                ),
                "priority": "required",
            }
        )

    has_reference = helpers.has_reference_material(state)
    reference_block = section_insert_prompt.format_reference_block(
        helpers.reference_text(state),
        has_reference=has_reference,
    )
    user_message = section_insert_prompt.build_user_message(
        topic_title=state.get("node_title", ""),
        teaching_instruction=helpers.teaching_instruction(state),
        document_outline=build_document_outline(document),
        missing_checklist_items=missing_items,
        topic_split=helpers.topic_split_for_targets(
            topic_split,
            missing_checklist_ids=sorted(missing_ids),
            checklist=checklist,
        ),
        domain=state.get("domain") or "",
        reference_block=reference_block,
    )
    return (
        section_insert_prompt.build_system_prompt(
            has_reference=has_reference,
            domain=state.get("domain"),
        ),
        user_message,
    )


async def _call_study_generator(
    *,
    system_prompt: str,
    user_message: str,
    revision: bool = False,
) -> Any:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    if revision:
        temperature = llm_settings.study_revision_temperature
        top_p = llm_settings.study_revision_top_p
        do_sample = llm_settings.study_revision_do_sample
    else:
        temperature = llm_settings.study_generation_temperature
        top_p = llm_settings.study_generation_top_p
        do_sample = llm_settings.study_generation_do_sample
    return await call_groq_with_rotation(
        messages=messages,
        model=llm_settings.llm_model,
        temperature=temperature,
        top_p=top_p,
        do_sample=do_sample,
        timeout=120,
        graph_node="study_generator",
        response_format={"type": "json_object"},
    )


def _uses_revision_sampling(
    state: StudyMaterialGraphState,
    retry_mode: str,
) -> bool:
    if retry_mode in helpers.SECTION_RETRY_MODES:
        return True
    mode = state.get("generation_mode") or "generate"
    return mode in ("regenerate", "improve")


async def _call_study_revision_llm(
    *,
    system_prompt: str,
    user_message: str,
) -> Any:
    return await _call_study_generator(
        system_prompt=system_prompt,
        user_message=user_message,
        revision=True,
    )


async def study_agent_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    if not helpers.groq_api_keys_configured():
        return {"error": "No GROQ API keys are configured."}

    retry_mode = helpers.qc_retry_mode(state)
    previous_document = (
        helpers.parse_current_document(state)
        if retry_mode == "full_regeneration"
        else None
    )
    rewrite_section_ids = set(state.get("qc_reverify_section_ids") or [])

    if retry_mode in helpers.SECTION_RETRY_MODES:
        return await helpers.run_section_retry(
            state,
            retry_mode,
            call_llm=_call_study_revision_llm,
            build_patch_messages=_build_section_patch_messages,
            build_insert_messages=_build_section_insert_messages,
        )

    system_prompt, user_message = _build_user_message(state)
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"

    result = await _call_study_generator(
        system_prompt=system_prompt,
        user_message=user_message,
        revision=_uses_revision_sampling(state, retry_mode),
    )
    if not result.ok:
        logger.error(
            "Groq study material generation failed: %s",
            result.error_type,
        )
        return helpers.study_llm_failure_return(
            state,
            result=result,
            prompt_snapshot=prompt_snapshot,
        )

    llm_model_used = result.model or llm_settings.llm_model
    token_usage = result.token_usage
    raw_content = result.content or ""

    try:
        cleaned_content = helpers.normalize_generator_output(raw_content)
    except ValueError as exc:
        logger.error("Generator returned invalid JSON: %s", exc)
        return {
            "generated_content": raw_content.strip(),
            "prompt_snapshot": prompt_snapshot,
            "token_usage": token_usage,
            "llm_model_used": llm_model_used,
            "llm_output_content": raw_content.strip(),
            "error": "Generator returned invalid JSON.",
        }

    mode = state.get("generation_mode") or "generate"
    doc = parse_generation_document(cleaned_content)
    if doc and is_reference_required_response(doc):
        cleaned_content = canonicalize_generation_json(cleaned_content)
    elif (
        retry_mode == "full_regeneration"
        and previous_document
        and doc
        and rewrite_section_ids
        and not is_reference_required_response(doc)
    ):
        merged = merge_full_regeneration_preserving_passing(
            doc,
            previous_document,
            rewrite_section_ids=rewrite_section_ids,
            topic_split=state.get("topic_split") or [],
        )
        cleaned_content = canonicalize_generation_json(json.dumps(merged))
        doc = merged
        if rewrite_section_ids:
            logger.info(
                "Full regeneration merge preserved %d passing section(s); rewrote %s",
                len(previous_document.get("sections") or []) - len(rewrite_section_ids),
                ", ".join(sorted(rewrite_section_ids)),
            )

    improve_status, regenerate_status = helpers.resolve_mode_status(mode, doc)

    helpers.log_study_output(
        state,
        generation_type=mode,
        result=result,
        cleaned_content=cleaned_content,
        prompt_snapshot=prompt_snapshot,
        llm_model_used=llm_model_used,
        token_usage=token_usage,
        improve_status=improve_status,
        regenerate_status=regenerate_status,
    )

    return {
        "generated_content": cleaned_content,
        "prompt_snapshot": prompt_snapshot,
        "token_usage": token_usage,
        "llm_model_used": llm_model_used,
        "improve_status": improve_status,
        "regenerate_status": regenerate_status,
        "llm_output_content": cleaned_content,
    }
