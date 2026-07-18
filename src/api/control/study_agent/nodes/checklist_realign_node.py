"""Post-research realign of draft concept checklist against ground-truth notes."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.concept import (
    build_checklist_realign_system_prompt,
    build_checklist_realign_user_message,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.data.repositories import NodeRepository
from src.api.schemas.study_material_schemas import parse_concept_checklist_response
from src.api.utils.external_research_utils.attach_sources import (
    attach_source_urls_to_node_media,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation
from src.api.utils.study_agent_utils.artifacts.study_material_artifacts import (
    log_agent_output,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    DEFAULT_INSTRUCTION,
    MAX_VERIFICATION_PARSE_RETRIES,
)

logger = logging.getLogger(__name__)

_REALIGN_JSON_REPROMPT = (
    "Your previous response was not valid JSON. "
    "Return ONLY the concept-plan JSON object with domain, topic_split, "
    "and must_cover_checklist fields."
)


def _draft_plan_return(state: StudyMaterialGraphState) -> dict[str, Any]:
    """Keep the pre-research draft plan unchanged."""
    return {
        "domain": state.get("domain") or "",
        "topic_split": state.get("topic_split") or [],
        "must_cover_checklist": state.get("must_cover_checklist") or [],
        "checklist_llm_model_used": state.get("checklist_llm_model_used"),
    }


def _research_notes_text(state: StudyMaterialGraphState) -> str:
    """Prefer ground_truth_reference; fall back to extracted_reference_text."""
    for key in ("ground_truth_reference", "extracted_reference_text"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _should_run_realign(state: StudyMaterialGraphState) -> bool:
    if state.get("reference_mode") != "external":
        return False
    if not _research_notes_text(state):
        return False
    checklist = state.get("must_cover_checklist")
    return bool(isinstance(checklist, list) and checklist)


async def _call_realign_llm(
    *,
    system_prompt: str,
    user_message: str,
) -> GroqCallResult:
    return await call_groq_with_rotation(
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        model=llm_settings.checklist_llm_model,
        temperature=0.0,
        timeout=60,
        graph_node="checklist_realign",
        response_format={"type": "json_object"},
    )


async def _generate_realigned_plan(
    *,
    system_prompt: str,
    user_message: str,
) -> tuple[GroqCallResult, str | None, int]:
    """Call Groq with key rotation and one JSON-reprompt retry on parse failure."""
    result = await _call_realign_llm(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    if not result.ok or not result.content:
        return result, None, 0

    parsed = parse_concept_checklist_response(result.content)
    if parsed is not None:
        return result, result.content, 0

    for attempt in range(MAX_VERIFICATION_PARSE_RETRIES):
        logger.warning(
            "checklist_realign_node: JSON parse failed — reprompting (attempt %d)",
            attempt + 1,
        )
        reprompt_result = await _call_realign_llm(
            system_prompt=_REALIGN_JSON_REPROMPT,
            user_message=(
                "Your previous response was not valid JSON. "
                "Return ONLY the concept-plan JSON object.\n\n"
                f"{user_message}"
            ),
        )
        result = reprompt_result
        if not result.ok or not result.content:
            return result, None, attempt + 1
        if parse_concept_checklist_response(result.content) is not None:
            return result, result.content, attempt + 1

    return result, result.content, MAX_VERIFICATION_PARSE_RETRIES


async def _maybe_attach_source_urls(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> None:
    """Idempotent re-attach of merge-surviving URLs (covers cache-hit path)."""
    if state.get("external_research_status") != "success":
        return

    source_urls = [url for url in (state.get("external_source_urls") or []) if url]
    if not source_urls:
        return

    configurable = config.get("configurable") or {}
    session = configurable.get("session")
    user_raw = configurable.get("user_id")
    node_id = state.get("node_id")
    if session is None or node_id is None or user_raw is None:
        return

    try:
        mentor_id = UUID(str(user_raw))
    except (TypeError, ValueError):
        return

    node_repo = NodeRepository(session)
    node = await node_repo.get_node_by_id(node_id)
    if node is None:
        return

    await attach_source_urls_to_node_media(
        session,
        node_id=node_id,
        space_id=cast(UUID, node.space_id),
        mentor_id=mentor_id,
        status=state.get("external_research_status"),
        source_urls=source_urls,
    )


async def checklist_realign_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Realign draft checklist against GT notes; fail-soft keeps the draft."""
    from src.api.schemas import GenerationPipeline
    from src.api.utils.generation_progress.reporter import maybe_report_node_enter

    await maybe_report_node_enter(
        config,
        "checklist_realign",
        default_pipeline=GenerationPipeline.STUDY_MATERIAL,
    )

    # Always attempt idempotent attach when URLs are present (cache-hit safety).
    await _maybe_attach_source_urls(state, config)

    if not _should_run_realign(state):
        logger.info(
            "checklist_realign_node: skipping LLM realign "
            "(reference_mode=%r, has_notes=%s, checklist_items=%d)",
            state.get("reference_mode"),
            bool(_research_notes_text(state)),
            len(state.get("must_cover_checklist") or []),
        )
        return _draft_plan_return(state)

    draft_domain = state.get("domain") or ""
    draft_topic_split = list(state.get("topic_split") or [])
    draft_checklist = list(state.get("must_cover_checklist") or [])
    draft_model = state.get("checklist_llm_model_used")

    if not helpers.groq_api_keys_configured():
        logger.warning(
            "checklist_realign_node: no GROQ API keys — keeping draft checklist"
        )
        return {
            "domain": draft_domain,
            "topic_split": draft_topic_split,
            "must_cover_checklist": draft_checklist,
            "checklist_llm_model_used": draft_model,
        }

    topic_title = state.get("node_title") or ""
    teaching_instruction = state.get("effective_instruction") or DEFAULT_INSTRUCTION
    research_notes = _research_notes_text(state)
    draft_plan = {
        "domain": draft_domain,
        "topic_split": draft_topic_split,
        "must_cover_checklist": draft_checklist,
    }

    system_prompt = build_checklist_realign_system_prompt()
    user_message = build_checklist_realign_user_message(
        topic_title,
        teaching_instruction=teaching_instruction,
        draft_plan=draft_plan,
        research_notes=research_notes,
    )
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"

    model = llm_settings.checklist_llm_model
    result, raw_response, parse_retries = await _generate_realigned_plan(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    checklist = draft_checklist
    topic_split = draft_topic_split
    domain = draft_domain
    model_used = draft_model
    used_draft = True
    llm_ok = result.ok
    llm_error_type: str | None = None if result.ok else result.error_type

    if not result.ok:
        logger.warning(
            "checklist_realign_node: Groq call failed (%s); keeping draft checklist",
            result.error_type,
        )
    elif raw_response:
        parsed = parse_concept_checklist_response(raw_response)
        if parsed is not None:
            # Domain is fixed from the draft — never reclassify.
            domain = draft_domain
            topic_split = parsed.topic_split_dicts
            checklist = parsed.must_cover_checklist_dicts
            model_used = result.model or model
            used_draft = False
            logger.info(
                "checklist_realign_node: realigned %d checklist items, "
                "%d topic_split sections (model=%s)",
                len(checklist),
                len(topic_split),
                model_used,
            )
        else:
            logger.warning(
                "checklist_realign_node: failed to parse LLM JSON after %d "
                "reprompt(s); keeping draft checklist. "
                "Raw response (first 300 chars): %.300s",
                parse_retries,
                raw_response,
            )

    run_id = state.get("artifact_run_id")
    if run_id:
        log_agent_output(
            topic_title=topic_title,
            run_id=run_id,
            agent="checklist_realign",
            node_id=str(state.get("node_id") or ""),
            generation_type=state.get("generation_mode") or "generate",
            payload={
                "llm_ok": llm_ok,
                "llm_error_type": llm_error_type,
                "llm_model_used": model_used,
                "used_draft": used_draft,
                "parse_retries": parse_retries,
                "provider_meta": result.provider_meta,
                "retry_after_seconds": result.retry_after_seconds,
                "next_llm_retry_at": result.next_llm_retry_at,
                "suggestion": result.suggestion,
                "domain": domain,
                "topic_split": topic_split,
                "must_cover_checklist": checklist,
                "raw_response": raw_response,
                "prompt_snapshot": prompt_snapshot,
            },
        )

    return {
        "domain": domain,
        "topic_split": topic_split,
        "must_cover_checklist": checklist,
        "checklist_llm_model_used": model_used,
    }
