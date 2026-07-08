# src/api/control/study_agent/nodes/study_agent_node.py
"""LangGraph study generator node — create, retry, improve, or regenerate material.

Pipeline position
-----------------
``concept_checklist`` → **study_agent** → ``quality_check``

Retry branches (``qc_retry_mode`` from last QC fail):
  - ``section_patch*`` → ``run_section_retry`` + ``section_rework_prompt``
  - ``full_regeneration`` → ``generation_prompt`` + ``<quality_check_feedback>``
  - ``none`` + mode ``generate`` → initial full document generation
  - mode ``improve`` / ``regenerate`` → mentor-driven prompts (separate from QC loop)

After full regen, ``merge_full_regeneration_preserving_passing`` may splice passing
sections from the previous draft (sections not in ``qc_reverify_section_ids``).
Section content hashes (P3/P4) invalidate stale frozen skips when bytes change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.generation import (
    generation_prompt,
    improve_prompt,
    regeneration_prompt,
)
from src.api.control.study_agent.prompts.section import (
    section_block_relocate_prompt,
    section_insert_prompt,
    section_rework_prompt,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    classify_generation_output,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
    merge_full_regeneration_preserving_passing,
)

logger = logging.getLogger(__name__)


def _build_user_message(state: StudyMaterialGraphState) -> tuple[str, str]:
    """Build system + user prompts for full-document generation paths.

    Uses ``generation_prompt`` when ``qc_retry_mode == full_regeneration`` or
    ``generation_mode == generate``. Otherwise improve/regenerate mentor prompts.

    QC feedback: only ``build_qc_feedback_block`` (flat text) for full_regen;
    section patch uses ``_build_section_patch_messages`` instead.
    """
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


def _uses_placement_relocate_prompt(state: StudyMaterialGraphState) -> bool:
    return state.get("qc_failure_class") == "placement_only"


def _build_section_patch_messages(
    state: StudyMaterialGraphState,
    document: dict[str, Any],
) -> tuple[str, str]:
    """Prompts for ``section_patch`` — rewrites failed sections only.

    Pulls ``qc_section_failures`` (structured bundles from ``classify_retry_routing``)
    into ``section_rework_prompt`` with ``<sections_to_fix>`` JSON, or into
    ``section_block_relocate_prompt`` when placement-only failures have low-confidence
    relocation plans for LLM fallback.
    """
    has_reference = helpers.has_reference_material(state)
    section_failures = state.get("qc_section_failures") or []
    patch_section_ids = helpers.section_ids_from_failures(section_failures)
    if _uses_placement_relocate_prompt(state):
        reference_block = section_block_relocate_prompt.format_reference_block(
            helpers.reference_text(state),
            has_reference=has_reference,
        )
        user_message = section_block_relocate_prompt.build_user_message(
            topic_title=state.get("node_title", ""),
            teaching_instruction=helpers.teaching_instruction(state),
            document_outline=build_document_outline(document),
            section_failures=section_failures,
            document=document,
            relocation_plans=state.get("qc_relocation_plans") or [],
            domain=state.get("domain") or "",
            topic_split_block=helpers.build_scoped_topic_split_block(
                state,
                section_ids=patch_section_ids,
            ),
            reference_block=reference_block,
        )
        return (
            section_block_relocate_prompt.build_system_prompt(
                has_reference=has_reference,
                domain=state.get("domain"),
            ),
            user_message,
        )

    reference_block = section_rework_prompt.format_reference_block(
        helpers.reference_text(state),
        has_reference=has_reference,
    )
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
    """Prompts for ``section_insert`` — writes missing checklist/topic_split sections.

    Targets ``qc_missing_checklist_ids`` from routing (structure gaps or must_cover
    items with no matching document section).
    """
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
    temperature: float | None = None,
) -> Any:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    if temperature is not None:
        temp = temperature
        top_p = llm_settings.study_revision_top_p
        do_sample = llm_settings.study_revision_do_sample
    elif revision:
        temp = llm_settings.study_revision_temperature
        top_p = llm_settings.study_revision_top_p
        do_sample = llm_settings.study_revision_do_sample
    else:
        temp = llm_settings.study_generation_temperature
        top_p = llm_settings.study_generation_top_p
        do_sample = llm_settings.study_generation_do_sample
    return await call_groq_with_rotation(
        messages=messages,
        model=llm_settings.llm_model,
        temperature=temp,
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
    state: StudyMaterialGraphState,
    *,
    system_prompt: str,
    user_message: str,
) -> Any:
    placement_relocate = _uses_placement_relocate_prompt(state)
    return await _call_study_generator(
        system_prompt=system_prompt,
        user_message=user_message,
        revision=True,
        temperature=0.1 if placement_relocate else None,
    )


def _make_section_patch_llm_call(
    state: StudyMaterialGraphState,
) -> Callable[..., Any]:
    async def _call(*, system_prompt: str, user_message: str) -> Any:
        return await _call_study_revision_llm(
            state,
            system_prompt=system_prompt,
            user_message=user_message,
        )

    return _call


async def study_agent_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Generate or revise study material JSON via Groq.

    Dispatches to ``run_section_retry`` for surgical QC retries, else full
    document generation/improve/regenerate. Classifies output via
    ``classify_generation_output`` (study_document | reference_required | malformed).
    """
    from src.api.schemas import GenerationPipeline
    from src.api.utils.generation_progress.reporter import maybe_report_node_enter

    await maybe_report_node_enter(
        config, "study_agent", default_pipeline=GenerationPipeline.STUDY_MATERIAL
    )

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
            call_llm=_make_section_patch_llm_call(state),
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
            "generation_outcome": "generator_error",
            "generation_outcome_detail": {"reason": "Generator returned invalid JSON."},
            "error": "Generator returned invalid JSON.",
        }

    classified = classify_generation_output(cleaned_content)
    outcome = classified.outcome
    canonical_json = classified.canonical_json
    doc = classified.document
    detail = classified.detail

    if (
        outcome == "study_document"
        and retry_mode == "full_regeneration"
        and previous_document
        and doc
        and rewrite_section_ids
    ):
        merged = merge_full_regeneration_preserving_passing(
            doc,
            previous_document,
            rewrite_section_ids=rewrite_section_ids,
            topic_split=state.get("topic_split") or [],
        )
        canonical_json = canonicalize_generation_json(json.dumps(merged))
        doc = merged
        if rewrite_section_ids:
            logger.info(
                "Full regeneration merge preserved %d passing section(s); rewrote %s",
                len(previous_document.get("sections") or []) - len(rewrite_section_ids),
                ", ".join(sorted(rewrite_section_ids)),
            )

    format_attempt = state.get("generator_format_attempt") or 0
    if outcome == "malformed_document":
        format_attempt += 1

    mode = state.get("generation_mode") or "generate"
    improve_status, regenerate_status = helpers.resolve_mode_status(mode, doc)

    helpers.log_study_output(
        state,
        generation_type=mode,
        result=result,
        cleaned_content=canonical_json,
        prompt_snapshot=prompt_snapshot,
        llm_model_used=llm_model_used,
        token_usage=token_usage,
        improve_status=improve_status,
        regenerate_status=regenerate_status,
    )

    return {
        "generated_content": canonical_json,
        "prompt_snapshot": prompt_snapshot,
        "token_usage": token_usage,
        "llm_model_used": llm_model_used,
        "improve_status": improve_status,
        "regenerate_status": regenerate_status,
        "llm_output_content": canonical_json,
        "generation_outcome": outcome,
        "generation_outcome_detail": detail,
        "generation_parsed_document": doc,
        "generator_format_attempt": format_attempt,
    }
