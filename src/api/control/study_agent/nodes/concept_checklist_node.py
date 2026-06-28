# src/api/control/study_agent/nodes/concept_checklist_node.py
"""Generates a dynamic must-cover checklist from the topic and teaching instruction."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config.llm_config import llm_settings
from src.api.control.study_agent.prompts.concept import (
    build_concept_checklist_system_prompt,
    build_concept_checklist_user_message,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.schemas.study_material_schemas.concept_checklist_schema import (
    fallback_checklist,
    fallback_topic_split,
    parse_concept_checklist_response,
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

_CHECKLIST_JSON_REPROMPT = (
    "Your previous response was not valid JSON. "
    "Return ONLY the concept-plan JSON object with domain, topic_split, "
    "and must_cover_checklist fields."
)


async def _call_checklist_llm(
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
        graph_node="concept_checklist",
        response_format={"type": "json_object"},
    )


async def _generate_concept_plan(
    *,
    system_prompt: str,
    user_message: str,
) -> tuple[GroqCallResult, str | None, int]:
    """Call Groq with key rotation and one JSON-reprompt retry on parse failure."""
    result = await _call_checklist_llm(
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
            "concept_checklist_node: JSON parse failed — reprompting (attempt %d)",
            attempt + 1,
        )
        reprompt_result = await _call_checklist_llm(
            system_prompt=_CHECKLIST_JSON_REPROMPT,
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


async def concept_checklist_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Generate the must-cover checklist and write it to state."""
    mode = state.get("generation_mode") or "generate"
    existing_checklist = state.get("must_cover_checklist")
    if existing_checklist and mode == "generate":
        logger.info(
            "concept_checklist_node: reusing concept plan from current generate run "
            "(%d checklist items)",
            len(existing_checklist),
        )
        return {
            "domain": state.get("domain") or "",
            "topic_split": state.get("topic_split") or [],
            "must_cover_checklist": existing_checklist,
            "checklist_llm_model_used": state.get("checklist_llm_model_used"),
        }

    if mode in ("improve", "regenerate"):
        logger.info(
            "concept_checklist_node: regenerating concept plan for %s run",
            mode,
        )

    if not helpers.groq_api_keys_configured():
        return {"error": "No GROQ API keys are configured."}

    topic_title = state.get("node_title") or ""
    teaching_instruction = state.get("effective_instruction") or DEFAULT_INSTRUCTION
    mentor_feedback = (state.get("mentor_feedback") or "").strip() or None

    parsed_data = state.get("parsed_reference_data") or {}
    sections = parsed_data.get("sections")
    reference_sections: list[dict[str, Any]] | None = None
    if isinstance(sections, list) and sections:
        reference_sections = sections

    previous_plan: dict[str, Any] | None = None
    if mode in ("improve", "regenerate") and existing_checklist:
        previous_plan = {
            "domain": state.get("domain") or "",
            "topic_split": state.get("topic_split") or [],
            "must_cover_checklist": existing_checklist,
        }

    system_prompt = build_concept_checklist_system_prompt(mode)
    user_message = build_concept_checklist_user_message(
        topic_title=topic_title,
        teaching_instruction=teaching_instruction,
        reference_sections=reference_sections,
        mentor_feedback=mentor_feedback,
        generation_mode=mode,
        previous_plan=previous_plan,
    )
    prompt_snapshot = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_message}"

    model = llm_settings.checklist_llm_model
    result, raw_response, parse_retries = await _generate_concept_plan(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    if not result.ok:
        logger.error(
            "concept_checklist_node: Groq call failed (%s); aborting pipeline.",
            result.error_type,
        )
        return helpers.checklist_llm_failure_return(
            state,
            result=result,
            prompt_snapshot=prompt_snapshot,
        )

    checklist: list[dict[str, Any]] | None = None
    topic_split: list[dict[str, Any]] | None = None
    domain: str = ""
    model_used = result.model or model
    llm_ok = True
    llm_error_type: str | None = None

    if raw_response:
        parsed = parse_concept_checklist_response(raw_response)
        if parsed is not None:
            checklist = parsed.must_cover_checklist_dicts
            topic_split = parsed.topic_split_dicts
            domain = parsed.domain
        else:
            logger.warning(
                "concept_checklist_node: failed to parse LLM JSON after %d reprompt(s); "
                "falling back to instruction-sentence heuristic. "
                "Raw response (first 300 chars): %.300s",
                parse_retries,
                raw_response,
            )

    used_fallback = checklist is None
    if checklist is None:
        checklist = fallback_checklist(teaching_instruction)
        topic_split = fallback_topic_split(checklist)
        model_used = "fallback"

    logger.info(
        "concept_checklist_node: generated %d checklist items, %d topic_split sections (model=%s)",
        len(checklist),
        len(topic_split or []),
        model_used,
    )

    run_id = state.get("artifact_run_id")
    if run_id:
        log_agent_output(
            topic_title=topic_title,
            run_id=run_id,
            agent="concept_checklist",
            node_id=str(state.get("node_id") or ""),
            generation_type=state.get("generation_mode") or "generate",
            payload={
                "llm_ok": llm_ok,
                "llm_error_type": llm_error_type,
                "llm_model_used": model_used,
                "used_fallback": used_fallback,
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
        "topic_split": topic_split or [],
        "must_cover_checklist": checklist,
        "checklist_llm_model_used": model_used,
    }
