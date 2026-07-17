"""Helpers for study agent graph nodes — parsing, logging, orchestration, and state.

Pipeline role
-------------
Shared utilities used by ``study_agent_node`` and ``quality_check_node``:

- **Prompt blocks:** topic_split, must_cover, domain, QC feedback (full regen)
- **Section retry:** ``run_section_retry`` orchestrates patch → merge → insert
- **QC state packaging:** ``base_qc_return``, ``routing_state``
- **Targeted QC scope:** ``reverify_section_ids_for_targeted``, ``checklist_for_reverify``

Retry modes (from ``classify_retry_routing``):
  ``section_patch`` | ``section_insert`` | ``section_patch_then_insert`` |
  ``full_regeneration`` | ``none``
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.generation import generation_prompt
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.schemas.qc_schemas import RetryRoutingResult
from src.api.schemas.study_material_schemas import (
    ConceptPlanOut,
    fallback_checklist,
    fallback_topic_split,
    parse_checklist,
    parse_concept_checklist_response,
)
from src.api.utils.LLM_utils.llm_failure_diagnostics import (
    STUDY_LLM_FAILURE_PLACEHOLDER,
    build_llm_failure_qc_result,
)
from src.api.utils.study_agent_utils.artifacts.study_material_artifacts import (
    log_agent_output,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    checklist_section_id,
    parse_generation_document,
    resolve_checklist_section_id,
    try_canonicalize_generation_json,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    DEFAULT_INSTRUCTION,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    insert_sections,
    merge_section_field_patches,
    merge_section_patches_scoped,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.qc_retry_audit import (
    build_study_retry_input_audit,
    should_attach_study_retry_audit,
)

logger = logging.getLogger(__name__)

NO_REFERENCE_PLACEHOLDER = "no reference material provided."

SECTION_RETRY_MODES = frozenset(
    {"section_patch", "section_insert", "section_patch_then_insert"}
)

LlmCall = Callable[..., Awaitable[Any]]
BuildMessages = Callable[[StudyMaterialGraphState, dict[str, Any]], tuple[str, str]]


def teaching_instruction(state: StudyMaterialGraphState) -> str:
    """Effective teaching mandate for generator/QC prompts (resolver output or default)."""
    return state.get("effective_instruction") or DEFAULT_INSTRUCTION


def has_reference_material(state: StudyMaterialGraphState) -> bool:
    """True when meaningful reference text is available for this run.

    PDF runs use ``reference_material_id`` / the ``has_reference_material`` flag.
    External research has no PDF id — non-empty ``extracted_reference_text`` counts
    when ``reference_mode == "external"`` or ``external_research_status == "success"``.
    """
    text = (state.get("extracted_reference_text") or "").strip()
    if not text or text.lower() == NO_REFERENCE_PLACEHOLDER:
        return False
    if (
        state.get("has_reference_material")
        or state.get("reference_material_id") is not None
    ):
        return True
    return (
        state.get("reference_mode") == "external"
        or state.get("external_research_status") == "success"
    )


def reference_kind(
    state: StudyMaterialGraphState,
) -> Literal["none", "pdf", "external"]:
    """Classify reference source for generator system/user prompt labeling.

    Returns ``external`` only when ``reference_mode == "external"`` and meaningful
    reference text is present; otherwise ``pdf`` when reference material exists,
    else ``none``.
    """
    if not has_reference_material(state):
        return "none"
    if state.get("reference_mode") == "external":
        return "external"
    return "pdf"


def reference_text(state: StudyMaterialGraphState) -> str:
    return (state.get("extracted_reference_text") or "").strip()


def qc_retry_mode(state: StudyMaterialGraphState) -> str:
    """Current retry mode from last QC fail; ``none`` when QC passed or not yet run."""
    return state.get("qc_retry_mode") or "none"


def groq_api_keys_configured() -> bool:
    """False when no Groq keys are available — nodes return early with error."""
    return bool(llm_settings.groq_api_keys())


def _target_section_ids_for_topic_split(
    *,
    section_ids: list[str] | set[str],
    missing_checklist_ids: list[str],
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]],
) -> set[str]:
    """Resolve document section ids for scoped topic_split / blueprint rows."""
    target: set[str] = {
        str(section_id).strip() for section_id in section_ids if str(section_id).strip()
    }
    topic_split_ids = {
        str(entry.get("id", "")).strip()
        for entry in topic_split
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    }
    for raw in missing_checklist_ids:
        missing_id = str(raw).strip()
        if not missing_id:
            continue
        if missing_id in topic_split_ids:
            target.add(missing_id)
            continue
        resolved = resolve_checklist_section_id(checklist, missing_id)
        if resolved:
            target.add(resolved)
        else:
            target.add(missing_id)
    return target


def topic_split_for_targets(
    topic_split: list[dict[str, Any]],
    *,
    section_ids: list[str] | set[str] | None = None,
    missing_checklist_ids: list[str] | None = None,
    checklist: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return topic_split entries for sections being patched, inserted, or re-verified."""
    if not topic_split:
        return []
    target_ids = _target_section_ids_for_topic_split(
        section_ids=section_ids or [],
        missing_checklist_ids=missing_checklist_ids or [],
        checklist=checklist or [],
        topic_split=topic_split,
    )
    if not target_ids:
        return []
    return [
        entry
        for entry in topic_split
        if isinstance(entry, dict) and str(entry.get("id", "")).strip() in target_ids
    ]


def build_topic_split_block(state: StudyMaterialGraphState) -> str:
    """Render the full topic_split blueprint for initial / full-document generation."""
    return generation_prompt.build_topic_split_block(state.get("topic_split") or [])


def build_scoped_topic_split_block(
    state: StudyMaterialGraphState,
    *,
    section_ids: list[str] | set[str] | None = None,
    missing_checklist_ids: list[str] | None = None,
) -> str:
    """Render topic_split rows only for sections in the current surgical retry scope."""
    scoped = topic_split_for_targets(
        state.get("topic_split") or [],
        section_ids=section_ids,
        missing_checklist_ids=missing_checklist_ids,
        checklist=state.get("must_cover_checklist") or [],
    )
    if not scoped:
        return ""
    return generation_prompt.build_topic_split_block(
        scoped,
        intro="Section blueprint for sections in scope for this retry:",
    )


def build_must_cover_block(state: StudyMaterialGraphState) -> str:
    """Render the must_cover_checklist block for the generator prompt."""
    return generation_prompt.build_must_cover_block(
        state.get("must_cover_checklist") or []
    )


def build_domain_block(state: StudyMaterialGraphState) -> str:
    """Render the domain classification block when available."""
    return generation_prompt.build_domain_block(state.get("domain") or "")


def build_qc_feedback_block(state: StudyMaterialGraphState) -> str:
    """Build ``<quality_check_feedback>`` block for **full_regeneration** only.

    Section patch retries use structured ``qc_section_failures`` in
    ``section_rework_prompt`` instead of this flat text block.

    Includes: formatted ``qc_feedback`` and previous draft JSON.
    Empty when ``qc_retry_mode`` is not ``full_regeneration`` or ``qc_attempt`` is 0.
    """
    if qc_retry_mode(state) != "full_regeneration":
        return ""

    qc_attempt = state.get("qc_attempt") or 0
    if qc_attempt == 0:
        return ""

    qc_feedback = (state.get("qc_feedback") or "").strip()
    if not qc_feedback:
        return ""

    parts = [f"\n<quality_check_feedback>\n{qc_feedback}\n</quality_check_feedback>"]

    previous_doc = (state.get("generated_content") or "").strip()
    if previous_doc:
        canonical = try_canonicalize_generation_json(previous_doc) or previous_doc
        parts.append(f"\n<previous_draft_json>\n{canonical}\n</previous_draft_json>")

    return "\n".join(parts)


def build_previous_failed_qc_feedback_block(state: StudyMaterialGraphState) -> str:
    """Build a prompt block for previously failed QC feedback from the database."""
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


def format_reference_block(
    has_reference: bool,
    reference_text_value: str,
    *,
    reference_kind: str = "none",
) -> str:
    """Wrap reference text for generator user messages."""
    return generation_prompt.format_reference_user_block(
        reference_text_value,
        has_reference=has_reference,
        reference_kind=reference_kind,
    )


def normalize_generator_output(raw: str) -> str:
    """Strip leading ``---`` and canonicalize study document JSON from LLM output."""
    cleaned = raw.strip()
    if cleaned.startswith("---"):
        cleaned = cleaned[3:].strip()
    return canonicalize_generation_json(cleaned)


def parse_current_document(state: StudyMaterialGraphState) -> dict[str, Any] | None:
    """Parse ``generated_content`` from state into a document dict, or None."""
    raw = (state.get("generated_content") or "").strip()
    if not raw:
        return None
    try:
        canonical = canonicalize_generation_json(raw)
    except ValueError:
        canonical = raw
    return parse_generation_document(canonical)


def extract_sections_from_response(raw: str) -> list[dict[str, Any]]:
    """Parse a sections-only LLM response into a list of section dicts."""
    cleaned = normalize_generator_output(raw)
    doc = parse_generation_document(cleaned)
    if not doc:
        raise ValueError("Section response is not valid JSON with a sections array")
    sections = doc.get("sections") or []
    if not isinstance(sections, list):
        raise ValueError("Section response missing sections array")
    return [section for section in sections if isinstance(section, dict)]


def resolve_mode_status(
    mode: str,
    doc: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Return (improve_status, regenerate_status) from a parsed JSON response."""
    from src.api.utils.study_agent_utils.generation.study_generation_json import (
        is_vague_improve_response,
        is_vague_regenerate_response,
    )

    if not doc:
        return None, None
    if is_vague_improve_response(doc):
        return "vague", None
    if is_vague_regenerate_response(doc):
        return None, "vague"
    if mode == "improve":
        return "generated", None
    if mode == "regenerate":
        return None, "generated"
    return None, None


def checklist_llm_failure_return(
    state: StudyMaterialGraphState,
    *,
    result: Any,
    prompt_snapshot: str,
) -> dict[str, Any]:
    """Return graph state when concept-checklist Groq call fails terminally."""
    run_id = state.get("artifact_run_id")
    gen_type = state.get("generation_mode") or "generate"
    if run_id:
        log_agent_output(
            topic_title=state.get("node_title") or str(state.get("node_id")),
            run_id=run_id,
            agent="concept_checklist",
            node_id=str(state.get("node_id") or ""),
            generation_type=gen_type,
            payload={
                "llm_ok": False,
                "llm_error_type": result.error_type,
                "llm_model_used": llm_settings.checklist_llm_model,
                "used_fallback": False,
                "provider_meta": result.provider_meta,
                "retry_after_seconds": result.retry_after_seconds,
                "next_llm_retry_at": result.next_llm_retry_at,
                "suggestion": result.suggestion,
                "prompt_snapshot": prompt_snapshot,
            },
        )
    return {
        "terminal_llm_failure": True,
        "llm_error_type": result.error_type,
        "provider_meta": result.provider_meta,
        "next_llm_retry_at": result.next_llm_retry_at,
        "qc_failed_permanently": True,
        "qc_result": build_llm_failure_qc_result(result),
        "generated_content": STUDY_LLM_FAILURE_PLACEHOLDER,
        "llm_output_content": STUDY_LLM_FAILURE_PLACEHOLDER,
        "checklist_llm_model_used": llm_settings.checklist_llm_model,
    }


def study_llm_failure_return(
    state: StudyMaterialGraphState,
    *,
    result: Any,
    prompt_snapshot: str,
    generation_type: str | None = None,
) -> dict[str, Any]:
    pipeline_attempt = (state.get("qc_attempt") or 0) + 1
    run_id = state.get("artifact_run_id")
    gen_type = generation_type or state.get("generation_mode") or "generate"
    if run_id:
        log_agent_output(
            topic_title=state.get("node_title") or str(state.get("node_id")),
            run_id=run_id,
            agent="study_generator",
            pipeline_attempt=pipeline_attempt,
            node_id=str(state.get("node_id") or ""),
            generation_type=gen_type,
            payload={
                "llm_ok": False,
                "llm_error_type": result.error_type,
                "content": STUDY_LLM_FAILURE_PLACEHOLDER,
                "prompt_snapshot": prompt_snapshot,
                "llm_model_used": llm_settings.llm_model,
                "token_usage": None,
            },
        )
    return {
        "terminal_llm_failure": True,
        "llm_error_type": result.error_type,
        "provider_meta": result.provider_meta,
        "next_llm_retry_at": result.next_llm_retry_at,
        "qc_failed_permanently": True,
        "qc_result": build_llm_failure_qc_result(result),
        "generated_content": STUDY_LLM_FAILURE_PLACEHOLDER,
        "prompt_snapshot": prompt_snapshot,
        "llm_model_used": llm_settings.llm_model,
        "llm_output_content": STUDY_LLM_FAILURE_PLACEHOLDER,
    }


def log_study_output(
    state: StudyMaterialGraphState,
    *,
    generation_type: str,
    result: Any,
    cleaned_content: str,
    prompt_snapshot: str,
    llm_model_used: str,
    token_usage: int | None,
    improve_status: str | None = None,
    regenerate_status: str | None = None,
    fixed_sections: list[dict[str, Any]] | None = None,
) -> None:
    run_id = state.get("artifact_run_id")
    if not run_id:
        return
    pipeline_attempt = (state.get("qc_attempt") or 0) + 1
    payload: dict[str, Any] = {
        "llm_ok": result.ok,
        "llm_error_type": result.error_type if not result.ok else None,
        "content": cleaned_content,
        "prompt_snapshot": prompt_snapshot,
        "llm_model_used": llm_model_used,
        "token_usage": token_usage,
        "improve_status": improve_status,
        "regenerate_status": regenerate_status,
    }
    if fixed_sections is not None:
        payload["fixed_sections"] = fixed_sections
        payload["qc_retry_mode"] = generation_type
    if should_attach_study_retry_audit(state):
        retry_audit = build_study_retry_input_audit(state)
        payload["retry_audit"] = retry_audit
        payload["triggered_by_qc_attempt"] = retry_audit["triggered_by_qc_attempt"]
        payload["retry_feedback_channel"] = retry_audit["retry_feedback_channel"]
    log_agent_output(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        run_id=run_id,
        agent="study_generator",
        pipeline_attempt=pipeline_attempt,
        node_id=str(state.get("node_id") or ""),
        generation_type=generation_type,
        payload=payload,
    )


class SectionCallError(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__("section LLM call failed")


async def call_and_parse_sections(
    state: StudyMaterialGraphState,
    *,
    call_llm: LlmCall,
    system_prompt: str,
    user_message: str,
    generation_type: str,
) -> tuple[list[dict[str, Any]], str, Any, str, int | None]:
    """Call Groq and return parsed sections plus metadata."""
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"
    result = await call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    if not result.ok:
        raise SectionCallError(
            study_llm_failure_return(
                state,
                result=result,
                prompt_snapshot=prompt_snapshot,
                generation_type=generation_type,
            )
        )

    llm_model_used = result.model or llm_settings.llm_model
    token_usage = result.token_usage
    raw_content = result.content or ""

    try:
        sections = extract_sections_from_response(raw_content)
    except ValueError as exc:
        logger.error("%s returned invalid JSON: %s", generation_type, exc)
        raise SectionCallError(
            {
                "generated_content": raw_content.strip(),
                "prompt_snapshot": prompt_snapshot,
                "token_usage": token_usage,
                "llm_model_used": llm_model_used,
                "llm_output_content": raw_content.strip(),
                "error": f"{generation_type} returned invalid JSON.",
            }
        ) from exc

    return sections, prompt_snapshot, result, llm_model_used, token_usage


async def run_section_retry(
    state: StudyMaterialGraphState,
    retry_mode: str,
    *,
    call_llm: LlmCall,
    build_patch_messages: BuildMessages,
    build_insert_messages: BuildMessages,
) -> dict[str, Any]:
    """Orchestrate surgical QC retries: section patch, insert, or both.

    Called from ``study_agent_node`` when ``qc_retry_mode`` is in
    ``SECTION_RETRY_MODES``.

    Flow:
    1. **section_patch** (or first half of patch_then_insert): LLM rewrites failed
       sections → ``merge_section_patches`` replaces whole section dicts by id.
    2. **section_insert**: LLM writes missing sections → ``insert_sections``.
    3. Sets ``fixed_sections`` for targeted QC on the next ``quality_check`` visit.

    Note: patch replaces **entire** section JSON per id — not line-level edits.
    Unfailed sections in the document are never sent to the LLM or merge step.

    Returns:
        Graph state update with ``generated_content``, ``fixed_sections``,
        ``generation_parsed_document``, etc.
    """
    document = parse_current_document(state)
    if not document:
        return {"error": "Cannot run section retry without a valid generated document."}

    fixed_sections: list[dict[str, Any]] = []
    merged_doc = document
    prompt_snapshots: list[str] = []
    total_token_usage: int | None = 0
    llm_model_used = llm_settings.llm_model
    last_result: Any = None

    try:
        if retry_mode in ("section_patch", "section_patch_then_insert"):
            failure_class = state.get("qc_failure_class")
            patch_jobs: list[tuple[list[dict[str, Any]], str, bool]] = []
            if failure_class == "mixed":
                placement_failures = list(
                    state.get("qc_placement_section_failures") or []
                )
                substance_failures = list(
                    state.get("qc_substance_section_failures") or []
                )
                if placement_failures:
                    patch_jobs.append((placement_failures, "placement_only", True))
                if substance_failures:
                    patch_jobs.append((substance_failures, "substance", False))
            else:
                use_field_merge = failure_class == "placement_only"
                patch_jobs.append(
                    (
                        list(state.get("qc_section_failures") or []),
                        str(failure_class or "substance"),
                        use_field_merge,
                    )
                )

            for section_failures, job_failure_class, use_field_merge in patch_jobs:
                if not section_failures:
                    continue
                patch_state = dict(state)
                patch_state["qc_section_failures"] = section_failures
                patch_state["qc_failure_class"] = job_failure_class
                system_prompt, user_message = build_patch_messages(
                    patch_state,
                    merged_doc,
                )
                (
                    patch_sections,
                    patch_snapshot,
                    patch_result,
                    patch_model,
                    patch_tokens,
                ) = await call_and_parse_sections(
                    patch_state,
                    call_llm=call_llm,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    generation_type="section_patch",
                )
                fixed_sections.extend(patch_sections)
                prompt_snapshots.append(patch_snapshot)
                last_result = patch_result
                llm_model_used = patch_model
                if patch_tokens is not None:
                    total_token_usage = (total_token_usage or 0) + patch_tokens

                if use_field_merge:
                    merge_result = merge_section_field_patches(
                        merged_doc,
                        patch_sections,
                    )
                else:
                    merge_result = merge_section_patches_scoped(
                        merged_doc,
                        patch_sections,
                        section_failures=section_failures,
                    )
                merged_doc = merge_result.document
                if merge_result.unmatched_patch_ids:
                    logger.warning(
                        "Unmatched section patch ids: %s",
                        ", ".join(merge_result.unmatched_patch_ids),
                    )

        if retry_mode in ("section_insert", "section_patch_then_insert"):
            system_prompt, user_message = build_insert_messages(state, merged_doc)
            (
                insert_sections_raw,
                insert_snapshot,
                insert_result,
                insert_model,
                insert_tokens,
            ) = await call_and_parse_sections(
                state,
                call_llm=call_llm,
                system_prompt=system_prompt,
                user_message=user_message,
                generation_type="section_insert",
            )
            fixed_sections.extend(insert_sections_raw)
            prompt_snapshots.append(insert_snapshot)
            last_result = insert_result
            llm_model_used = insert_model
            if insert_tokens is not None:
                total_token_usage = (total_token_usage or 0) + insert_tokens

            merged_doc = insert_sections(merged_doc, insert_sections_raw)

    except SectionCallError as exc:
        return exc.payload

    cleaned_content = canonicalize_generation_json(json.dumps(merged_doc))
    prompt_snapshot = "\n\n---\n\n".join(prompt_snapshots)

    log_study_output(
        state,
        generation_type=retry_mode,
        result=last_result,
        cleaned_content=cleaned_content,
        prompt_snapshot=prompt_snapshot,
        llm_model_used=llm_model_used,
        token_usage=total_token_usage,
        fixed_sections=fixed_sections,
    )

    return {
        "generated_content": cleaned_content,
        "prompt_snapshot": prompt_snapshot,
        "token_usage": total_token_usage,
        "llm_model_used": llm_model_used,
        "llm_output_content": cleaned_content,
        "fixed_sections": fixed_sections,
        "generation_outcome": "study_document",
        "generation_outcome_detail": {},
        "generation_parsed_document": merged_doc,
    }


def routing_state(
    routing: RetryRoutingResult | None = None,
    *,
    clear: bool = False,
    qc_relocation_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map ``RetryRoutingResult`` into graph state fields for the study agent.

    On QC **pass** (``clear=True``): resets ``qc_retry_mode`` to ``none`` and
    clears reverify/missing/failure bundles.

    On QC **fail**: writes ``qc_retry_mode``, ``qc_reverify_section_ids``,
    ``qc_missing_checklist_ids``, ``qc_section_failures`` for ``study_agent_node``.
    """
    if clear:
        return {
            "qc_retry_mode": "none",
            "qc_reverify_section_ids": [],
            "qc_missing_checklist_ids": [],
            "qc_section_failures": [],
            "qc_failure_class": None,
            "qc_relocation_plans": None,
            "qc_placement_section_failures": None,
            "qc_substance_section_failures": None,
        }
    assert routing is not None
    return {
        "qc_retry_mode": routing.mode,
        "qc_reverify_section_ids": routing.failed_section_ids,
        "qc_missing_checklist_ids": routing.missing_checklist_ids,
        "qc_section_failures": routing.section_failures,
        "qc_failure_class": routing.failure_class,
        "qc_relocation_plans": qc_relocation_plans,
        "qc_placement_section_failures": routing.placement_section_failures,
        "qc_substance_section_failures": routing.substance_section_failures,
    }


def section_ids_from_failures(section_failures: list[dict[str, Any]]) -> list[str]:
    """Extract document section ids from QC section failure bundles."""
    return [
        str(bundle.get("section_id", "")).strip()
        for bundle in section_failures
        if isinstance(bundle, dict) and str(bundle.get("section_id", "")).strip()
    ]


def checklist_for_reverify(
    checklist: list[dict[str, Any]],
    *,
    section_ids: list[str],
    missing_checklist_ids: list[str],
) -> list[dict[str, Any]]:
    """Filter must_cover checklist to items in targeted QC scope only."""
    target_ids = set(section_ids) | set(missing_checklist_ids)
    if not target_ids:
        return checklist
    return [
        item
        for item in checklist
        if item.get("id") in target_ids or checklist_section_id(item) in target_ids
    ]


def reverify_section_ids_for_targeted(state: StudyMaterialGraphState) -> list[str]:
    """Section ids to re-verify on targeted QC pass 2.

    Union of ``qc_reverify_section_ids`` (from routing) and ids from
    ``fixed_sections`` (newly inserted sections must be verified too).
    """
    section_ids = list(state.get("qc_reverify_section_ids") or [])
    fixed_sections = state.get("fixed_sections") or []
    for section in fixed_sections:
        if isinstance(section, dict):
            section_id = str(section.get("id", "")).strip()
            if section_id and section_id not in section_ids:
                section_ids.append(section_id)
    return section_ids


def base_qc_return(
    *,
    new_attempt: int,
    generated_content: str,
    qc_result: dict[str, Any],
    model_used: str,
    models_used: dict[str, str | None],
    extraction_snapshot: dict[str, Any],
    verification_mode: str,
    frozen_check_ids: list[str] | None = None,
    frozen_section_ids: list[str] | None = None,
    section_content_hashes: dict[str, str] | None = None,
    fixed_sections: list[dict[str, Any]] | None = None,
    routing: RetryRoutingResult | None = None,
    routing_clear: bool = False,
    qc_relocation_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Package shared QC state fields returned by ``quality_check_node``.

    Does **not** include pass/fail-specific keys (``qc_passed``, ``qc_feedback``,
    ``qc_failed_permanently``) — the node adds those.

    Always spreads ``routing_state`` (clear on pass, routing on fail).
    Frozen fields and ``qc_section_content_hashes`` are written when provided
    (both full and targeted passes after P3/P4).

    ``fixed_sections`` is always cleared here (``None``) so patch output from
    study_agent is consumed once; study_agent sets it on retry.
    """
    payload: dict[str, Any] = {
        "generated_content": generated_content,
        "qc_result": qc_result,
        "qc_attempt": new_attempt,
        "qc_extraction": extraction_snapshot,
        "qc_llm_model_used": model_used,
        "qc_llm_models_used": models_used,
        "qc_verification_mode": verification_mode,
        "fixed_sections": fixed_sections,
        **routing_state(
            routing,
            clear=routing_clear,
            qc_relocation_plans=qc_relocation_plans,
        ),
    }
    if frozen_check_ids is not None:
        payload["qc_frozen_check_ids"] = frozen_check_ids
    if frozen_section_ids is not None:
        payload["qc_frozen_section_keys"] = frozen_section_ids
    if section_content_hashes is not None:
        payload["qc_section_content_hashes"] = section_content_hashes
    return payload


__all__ = [
    "ConceptPlanOut",
    "fallback_checklist",
    "fallback_topic_split",
    "parse_checklist",
    "parse_concept_checklist_response",
]
