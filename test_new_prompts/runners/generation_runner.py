"""Study material generation runner — uses test_new_prompts/prompts/generation_prompt.py."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config.llm_config import llm_settings
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from test_new_prompts.runners._prompt_loader import load_prompt_module
from test_new_prompts.runners._run_output import write_json, write_text
from test_new_prompts.runners._types import (
    ChecklistRunResult,
    GenerationRunResult,
    PromptTestInputs,
)

logger = logging.getLogger(__name__)


async def _call_generation_llm(
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
        temperature=llm_settings.study_generation_temperature,
        top_p=llm_settings.study_generation_top_p,
        do_sample=llm_settings.study_generation_do_sample,
        timeout=120,
        graph_node="study_generator",
        response_format={"type": "json_object"},
    )


def _normalize_output(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("---"):
        cleaned = cleaned[3:].strip()
    return canonicalize_generation_json(cleaned)


async def run_generation(
    *,
    run_dir: Any,
    inputs: PromptTestInputs,
    checklist: ChecklistRunResult,
) -> GenerationRunResult:
    """Run study material generation using checklist outputs and the new prompt template."""
    output_dir = run_dir / "generation"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)

    if not helpers.groq_api_keys_configured():
        finished_at = datetime.now(UTC)
        error = "No GROQ API keys are configured."
        write_json(
            output_dir / "metadata.json",
            {
                "stage": "generation",
                "ok": False,
                "error": error,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
            },
        )
        return GenerationRunResult(ok=False, output_dir=output_dir, error=error)

    if not checklist.ok:
        error = "Concept checklist did not succeed; cannot run generation."
        write_json(
            output_dir / "metadata.json",
            {"stage": "generation", "ok": False, "error": error},
        )
        return GenerationRunResult(ok=False, output_dir=output_dir, error=error)

    generation_prompt = load_prompt_module("generation_prompt")
    has_reference = False
    domain_block = generation_prompt.build_domain_block(checklist.domain)
    topic_split_block = generation_prompt.build_topic_split_block(checklist.topic_split)
    must_cover_block = generation_prompt.build_must_cover_block(
        checklist.must_cover_checklist
    )
    reference_block = generation_prompt.format_reference_user_block(
        "", has_reference=has_reference
    )

    system_prompt = generation_prompt.build_system_prompt(
        has_reference=has_reference,
        domain=checklist.domain or None,
    )
    user_message = generation_prompt.build_user_message(
        topic_title=inputs.topic,
        teaching_instruction_text=inputs.effective_instruction,
        must_cover_block=must_cover_block,
        topic_split_block=topic_split_block,
        domain_block=domain_block,
        reference_block=reference_block,
    )

    write_text(output_dir / "system_prompt.txt", system_prompt)
    write_text(output_dir / "user_message.txt", user_message)

    result = await _call_generation_llm(
        system_prompt=system_prompt,
        user_message=user_message,
    )
    finished_at = datetime.now(UTC)

    metadata: dict[str, Any] = {
        "stage": "generation",
        "topic": inputs.topic,
        "effective_instruction": inputs.effective_instruction,
        "domain": checklist.domain,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "llm_ok": result.ok,
        "llm_error_type": result.error_type,
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
        "provider_meta": result.provider_meta,
        "suggestion": result.suggestion,
    }

    raw_content = result.content or ""
    if raw_content:
        write_text(output_dir / "raw_response.json", raw_content)

    if not result.ok:
        metadata["ok"] = False
        metadata["error"] = result.error_type or "LLM call failed"
        write_json(output_dir / "metadata.json", metadata)
        return GenerationRunResult(
            ok=False,
            output_dir=output_dir,
            metadata=metadata,
            error=metadata["error"],
        )

    generated_content = raw_content
    parse_ok = False
    try:
        generated_content = _normalize_output(raw_content)
        write_text(output_dir / "parsed_content.json", generated_content)
        parse_ok = True
    except ValueError as exc:
        logger.warning("Generation JSON canonicalization failed: %s", exc)
        metadata["parse_warning"] = str(exc)

    metadata["parse_ok"] = parse_ok
    metadata["ok"] = True
    write_json(output_dir / "metadata.json", metadata)

    logger.info("Generation complete (parse_ok=%s)", parse_ok)
    return GenerationRunResult(
        ok=True,
        output_dir=output_dir,
        generated_content=generated_content,
        metadata=metadata,
    )
