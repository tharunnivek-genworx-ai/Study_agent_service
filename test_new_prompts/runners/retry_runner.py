"""QC-driven retry runner — section patch/insert and full regeneration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config.llm_config import llm_settings
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    parse_generation_document,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
    extract_sections_by_ids,
    merge_full_regeneration_preserving_passing,
)
from test_new_prompts.runners._prompt_loader import load_prompt_module
from test_new_prompts.runners._run_output import write_json, write_text
from test_new_prompts.runners._types import (
    ChecklistRunResult,
    PromptTestInputs,
    RetryRunResult,
)

logger = logging.getLogger(__name__)


async def _call_revision_llm(
    *,
    system_prompt: str,
    user_message: str,
) -> GroqCallResult:
    return await call_groq_with_rotation(
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        model=llm_settings.llm_model,
        temperature=llm_settings.study_revision_temperature,
        top_p=llm_settings.study_revision_top_p,
        do_sample=llm_settings.study_revision_do_sample,
        timeout=120,
        graph_node="study_generator",
        response_format={"type": "json_object"},
    )


def _build_section_patch_messages(
    state: StudyMaterialGraphState,
    document: dict[str, Any],
    *,
    section_rework_prompt: Any,
) -> tuple[str, str]:
    section_failures = state.get("qc_section_failures") or []
    patch_section_ids = helpers.section_ids_from_failures(section_failures)
    sections_content = extract_sections_by_ids(document, patch_section_ids)
    scoped_checklist = helpers.checklist_for_reverify(
        state.get("must_cover_checklist") or [],
        section_ids=patch_section_ids,
        missing_checklist_ids=[],
    )
    scoped_topic_split = helpers.topic_split_for_targets(
        state.get("topic_split") or [],
        section_ids=patch_section_ids,
        checklist=state.get("must_cover_checklist") or [],
    )
    user_message = section_rework_prompt.build_user_message(
        topic_title=state.get("node_title", ""),
        teaching_instruction=helpers.teaching_instruction(state),
        section_failures=section_failures,
        sections_content=sections_content,
        must_cover_checklist=scoped_checklist,
        topic_split=scoped_topic_split,
        domain=state.get("domain") or "",
    )
    return (
        section_rework_prompt.build_system_prompt(
            has_reference=False,
            domain=state.get("domain"),
        ),
        user_message,
    )


def _build_section_insert_messages(
    state: StudyMaterialGraphState,
    document: dict[str, Any],
    *,
    section_insert_prompt: Any,
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
    )
    return (
        section_insert_prompt.build_system_prompt(
            has_reference=False,
            domain=state.get("domain"),
        ),
        user_message,
    )


async def _run_full_regeneration(
    *,
    state: StudyMaterialGraphState,
    generation_prompt: Any,
) -> dict[str, Any]:
    has_reference = False
    domain_block = generation_prompt.build_domain_block(state.get("domain") or "")
    topic_split_block = generation_prompt.build_topic_split_block(
        state.get("topic_split") or []
    )
    must_cover_block = generation_prompt.build_must_cover_block(
        state.get("must_cover_checklist") or []
    )
    reference_block = generation_prompt.format_reference_user_block(
        "", has_reference=has_reference
    )
    qc_fix_block = helpers.build_qc_feedback_block(state)

    system_prompt = generation_prompt.build_system_prompt(
        has_reference=has_reference,
        domain=state.get("domain"),
    )
    user_message = generation_prompt.build_user_message(
        topic_title=state.get("node_title", ""),
        teaching_instruction_text=helpers.teaching_instruction(state),
        must_cover_block=must_cover_block,
        topic_split_block=topic_split_block,
        domain_block=domain_block,
        reference_block=reference_block,
        qc_fix_block=qc_fix_block,
    )
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"

    result = await _call_revision_llm(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    if not result.ok:
        return {
            "error": result.error_type or "Full regeneration LLM call failed",
            "prompt_snapshot": prompt_snapshot,
            "llm_model_used": result.model or llm_settings.llm_model,
        }

    raw_content = result.content or ""
    try:
        cleaned = helpers.normalize_generator_output(raw_content)
    except ValueError as exc:
        return {
            "error": f"Full regeneration returned invalid JSON: {exc}",
            "prompt_snapshot": prompt_snapshot,
            "generated_content": raw_content.strip(),
            "llm_model_used": result.model or llm_settings.llm_model,
        }

    previous_document = helpers.parse_current_document(state)
    rewrite_section_ids = set(state.get("qc_reverify_section_ids") or [])
    doc = parse_generation_document(cleaned)
    if previous_document and doc and rewrite_section_ids:
        merged = merge_full_regeneration_preserving_passing(
            doc,
            previous_document,
            rewrite_section_ids=rewrite_section_ids,
            topic_split=state.get("topic_split") or [],
        )
        cleaned = canonicalize_generation_json(json.dumps(merged))

    return {
        "generated_content": cleaned,
        "prompt_snapshot": prompt_snapshot,
        "token_usage": result.token_usage,
        "llm_model_used": result.model or llm_settings.llm_model,
        "fixed_sections": None,
    }


async def run_retry(
    *,
    run_dir: Any,
    attempt: int,
    retry_mode: str,
    inputs: PromptTestInputs,
    checklist: ChecklistRunResult,
    pipeline_state: dict[str, Any],
) -> RetryRunResult:
    """Execute a QC-routed retry using test_new_prompts section/regeneration templates."""
    output_dir = run_dir / "retry" / f"attempt_{attempt:02d}_{retry_mode}"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)

    if not helpers.groq_api_keys_configured():
        error = "No GROQ API keys are configured."
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return RetryRunResult(
            ok=False,
            output_dir=output_dir,
            retry_mode=retry_mode,
            attempt=attempt,
            error=error,
        )

    if retry_mode == "none":
        error = "No retry mode to execute."
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return RetryRunResult(
            ok=False,
            output_dir=output_dir,
            retry_mode=retry_mode,
            attempt=attempt,
            error=error,
        )

    write_json(
        output_dir / "routing_input.json",
        {
            "retry_mode": retry_mode,
            "qc_reverify_section_ids": pipeline_state.get("qc_reverify_section_ids"),
            "qc_missing_checklist_ids": pipeline_state.get("qc_missing_checklist_ids"),
            "qc_section_failures": pipeline_state.get("qc_section_failures"),
            "qc_feedback": pipeline_state.get("qc_feedback"),
        },
    )

    state: StudyMaterialGraphState = pipeline_state  # type: ignore[assignment]
    generation_prompt = load_prompt_module("generation_prompt")
    section_rework_prompt = load_prompt_module("section_rework_prompt")
    section_insert_prompt = load_prompt_module("section_insert_prompt")

    result: dict[str, Any]
    if retry_mode == "full_regeneration":
        result = await _run_full_regeneration(
            state=state,
            generation_prompt=generation_prompt,
        )
    elif retry_mode in helpers.SECTION_RETRY_MODES:
        result = await helpers.run_section_retry(
            state,
            retry_mode,
            call_llm=_call_revision_llm,
            build_patch_messages=lambda s, doc: _build_section_patch_messages(
                s, doc, section_rework_prompt=section_rework_prompt
            ),
            build_insert_messages=lambda s, doc: _build_section_insert_messages(
                s, doc, section_insert_prompt=section_insert_prompt
            ),
        )
    else:
        error = f"Unsupported retry mode: {retry_mode}"
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return RetryRunResult(
            ok=False,
            output_dir=output_dir,
            retry_mode=retry_mode,
            attempt=attempt,
            error=error,
        )

    finished_at = datetime.now(UTC)
    metadata: dict[str, Any] = {
        "stage": "retry",
        "retry_mode": retry_mode,
        "attempt": attempt,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
    }

    if result.get("error"):
        metadata["ok"] = False
        metadata["error"] = result["error"]
        if snapshot := result.get("prompt_snapshot"):
            write_text(output_dir / "prompt_snapshot.txt", snapshot)
        write_json(output_dir / "metadata.json", metadata)
        return RetryRunResult(
            ok=False,
            output_dir=output_dir,
            retry_mode=retry_mode,
            attempt=attempt,
            metadata=metadata,
            error=str(result["error"]),
        )

    generated_content = result.get("generated_content") or ""
    if snapshot := result.get("prompt_snapshot"):
        write_text(output_dir / "prompt_snapshot.txt", snapshot)
    if generated_content:
        write_text(output_dir / "parsed_content.json", generated_content)
    if fixed := result.get("fixed_sections"):
        write_json(output_dir / "fixed_sections.json", fixed)

    metadata.update(
        {
            "ok": True,
            "llm_model_used": result.get("llm_model_used"),
            "token_usage": result.get("token_usage"),
            "fixed_section_count": len(result.get("fixed_sections") or []),
        }
    )
    write_json(output_dir / "metadata.json", metadata)

    logger.info("Retry %s complete (attempt %d)", retry_mode, attempt)
    return RetryRunResult(
        ok=True,
        output_dir=output_dir,
        retry_mode=retry_mode,
        attempt=attempt,
        generated_content=generated_content,
        fixed_sections=result.get("fixed_sections"),
        metadata=metadata,
    )
