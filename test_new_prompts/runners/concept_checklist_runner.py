"""Concept checklist runner — uses test_new_prompts/prompts/concept_checklist_prompt.py."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config.llm_config import llm_settings
from src.api.schemas.study_material_schemas.concept_checklist_schema import (
    parse_concept_checklist_response,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_VERIFICATION_PARSE_RETRIES,
)
from test_new_prompts.runners._prompt_loader import load_prompt_module
from test_new_prompts.runners._run_output import write_json, write_text
from test_new_prompts.runners._types import ChecklistRunResult, PromptTestInputs

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
    result = await _call_checklist_llm(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    if not result.ok or not result.content:
        return result, None, 0

    if parse_concept_checklist_response(result.content) is not None:
        return result, result.content, 0

    for attempt in range(MAX_VERIFICATION_PARSE_RETRIES):
        logger.warning(
            "concept_checklist_runner: JSON parse failed — reprompting (attempt %d)",
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


def _build_metadata(
    *,
    started_at: datetime,
    finished_at: datetime,
    result: GroqCallResult,
    parse_retries: int,
    model_setting: str,
) -> dict[str, Any]:
    return {
        "stage": "concept_checklist",
        "topic": None,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "llm_ok": result.ok,
        "llm_error_type": result.error_type,
        "llm_model_used": result.model or model_setting,
        "token_usage": result.token_usage,
        "parse_retries": parse_retries,
        "provider_meta": result.provider_meta,
        "suggestion": result.suggestion,
    }


async def run_concept_checklist(
    *,
    run_dir: Any,
    inputs: PromptTestInputs,
) -> ChecklistRunResult:
    """Run concept checklist using the new prompt template."""
    output_dir = run_dir / "concept_checklist"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)

    if not helpers.groq_api_keys_configured():
        finished_at = datetime.now(UTC)
        error = "No GROQ API keys are configured."
        write_json(
            output_dir / "metadata.json",
            {
                "stage": "concept_checklist",
                "ok": False,
                "error": error,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
            },
        )
        return ChecklistRunResult(
            ok=False,
            output_dir=output_dir,
            error=error,
        )

    checklist_prompt = load_prompt_module("concept_checklist_prompt")
    system_prompt = checklist_prompt.SYSTEM_PROMPT
    user_message = checklist_prompt.build_user_message(
        topic_title=inputs.topic,
        teaching_instruction=inputs.effective_instruction,
    )

    write_text(output_dir / "system_prompt.txt", system_prompt)
    write_text(output_dir / "user_message.txt", user_message)

    model_setting = llm_settings.checklist_llm_model
    result, raw_response, parse_retries = await _generate_concept_plan(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    finished_at = datetime.now(UTC)

    metadata = _build_metadata(
        started_at=started_at,
        finished_at=finished_at,
        result=result,
        parse_retries=parse_retries,
        model_setting=model_setting,
    )
    metadata["topic"] = inputs.topic
    metadata["effective_instruction"] = inputs.effective_instruction

    if raw_response:
        write_text(output_dir / "raw_response.json", raw_response)

    if not result.ok:
        metadata["ok"] = False
        metadata["error"] = result.error_type or "LLM call failed"
        write_json(output_dir / "metadata.json", metadata)
        return ChecklistRunResult(
            ok=False,
            output_dir=output_dir,
            raw_response=raw_response,
            metadata=metadata,
            error=metadata["error"],
        )

    parsed = parse_concept_checklist_response(raw_response or "")
    if parsed is None:
        metadata["ok"] = False
        metadata["error"] = "Failed to parse concept checklist JSON after reprompt"
        write_json(output_dir / "metadata.json", metadata)
        return ChecklistRunResult(
            ok=False,
            output_dir=output_dir,
            raw_response=raw_response,
            metadata=metadata,
            error=metadata["error"],
        )

    parsed_plan = {
        "domain": parsed.domain,
        "topic_split": parsed.topic_split_dicts,
        "must_cover_checklist": parsed.must_cover_checklist_dicts,
    }
    write_json(output_dir / "parsed_plan.json", parsed_plan)

    metadata.update(
        {
            "ok": True,
            "domain": parsed.domain,
            "topic_split_count": len(parsed.topic_split),
            "must_cover_count": len(parsed.must_cover_checklist),
        }
    )
    write_json(output_dir / "metadata.json", metadata)

    logger.info(
        "Concept checklist complete: domain=%s, sections=%d, items=%d",
        parsed.domain,
        len(parsed.topic_split),
        len(parsed.must_cover_checklist),
    )

    return ChecklistRunResult(
        ok=True,
        output_dir=output_dir,
        domain=parsed.domain,
        topic_split=parsed.topic_split_dicts,
        must_cover_checklist=parsed.must_cover_checklist_dicts,
        raw_response=raw_response,
        parsed_plan=parsed_plan,
        metadata=metadata,
    )
