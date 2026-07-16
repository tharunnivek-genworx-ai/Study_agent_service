"""Generate or surgically retry quiz questions based on qc_retry_mode.

Graph node (generate/regenerate loop)
-------------------------------------
Central LLM node. On first pass builds a full quiz prompt; on QC/struct retries
delegates to ``run_question_retry`` for patch/insert modes or regenerates with
combined ``gen_feedback`` / ``qc_feedback``.

Routing (via ``_route_after_quiz_generator``)
---------------------------------------------
- ``terminal_llm_failure`` → ``persist_quiz_draft``
- ``error`` → END
- ``parsed_questions`` set → ``deterministic_validate`` (else ``parse_quiz_output``)

Key state fields written: ``raw_llm_output``, ``parsed_questions``,
``validated_questions`` (retry path), ``quiz_title``, ``fixed_questions``.
"""

from __future__ import annotations

import logging
from typing import Any

from src.api.config import llm_settings
from src.api.control.quiz_agent.prompts import build_quiz_prompt
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.LLM_utils.llm_failure_diagnostics import build_llm_failure_qc_result
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)
from src.api.utils.quiz_utils.graph.constants import (
    QUESTION_PRUNE_MODE,
    QUESTION_RETRY_MODES,
)
from src.api.utils.quiz_utils.graph.node_helpers import (
    call_quiz_llm,
    log_quiz_artifact,
    qc_retry_mode,
    run_question_prune,
    run_question_retry,
)
from src.api.utils.quiz_utils.quality_check_utils.document.question_merge import (
    merge_full_regeneration_preserving_passing,
)

logger = logging.getLogger(__name__)


async def quiz_generator_node(state: QuizGraphState) -> dict[str, Any]:
    """Generate or surgically retry quiz questions based on ``qc_retry_mode``."""
    retry_mode = qc_retry_mode(state)
    previous_questions = (
        list(state.get("validated_questions") or state.get("parsed_questions") or [])
        if retry_mode == "full_regeneration"
        else None
    )
    rewrite_question_ids = set(state.get("qc_reverify_question_ids") or [])

    if retry_mode == QUESTION_PRUNE_MODE:
        result = await run_question_prune(state, call_llm=call_quiz_llm)
        log_quiz_artifact(
            state,
            "quiz_generator",
            {
                "raw_llm_output": result.get("raw_llm_output"),
                "parsed_questions": result.get("parsed_questions"),
                "qc_retry_mode": retry_mode,
                "gen_attempt": state.get("gen_attempt") or 0,
                "present_without_qc": result.get("present_without_qc"),
                "error": result.get("error"),
            },
        )
        return result

    if retry_mode in QUESTION_RETRY_MODES:
        # Surgical retry: patch and/or insert without full regeneration.
        result = await run_question_retry(
            state,
            retry_mode,
            call_llm=call_quiz_llm,
        )
        log_quiz_artifact(
            state,
            "quiz_generator",
            {
                "raw_llm_output": result.get("raw_llm_output"),
                "parsed_questions": result.get("parsed_questions"),
                "qc_retry_mode": result.get("qc_retry_mode") or retry_mode,
                "gen_attempt": state.get("gen_attempt") or 0,
                "error": result.get("error"),
            },
        )
        return result

    qc_attempt = state.get("qc_attempt") or 0
    gen_attempt = state.get("gen_attempt") or 0
    qc_feedback = (state.get("qc_feedback") or "").strip() if qc_attempt > 0 else None
    gen_feedback = (
        (state.get("gen_feedback") or "").strip() if gen_attempt > 0 else None
    )
    combined_feedback = (
        "\n\n".join(part for part in (gen_feedback, qc_feedback) if part) or None
    )

    prompt_input = build_quiz_prompt(
        node_title=state.get("node_title"),
        study_material_content=state.get("study_material_content"),
        question_count=state["question_count"],
        difficulty=state["difficulty"],
        mode=state.get("mode", "generate"),
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
        existing_quiz_questions=state.get("existing_quiz_questions"),
        mentor_feedback=state.get("mentor_feedback"),
        qc_feedback=combined_feedback,
        failed_qc_feedback=state.get("failed_qc_feedback"),
    )

    result = await call_quiz_llm(
        system_prompt=prompt_input["system_prompt"],
        user_message=prompt_input["user_message"],
        question_count=state["question_count"],
    )
    if not result.ok:
        logger.error("Groq quiz generation failed: %s", result.error_type)
        failure = {
            "terminal_llm_failure": True,
            "llm_error_type": result.error_type,
            "provider_meta": result.provider_meta,
            "next_llm_retry_at": result.next_llm_retry_at,
            "qc_failed_permanently": True,
            "qc_result": build_llm_failure_qc_result(result),
            "validated_questions": [],
            "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
        }
        log_quiz_artifact(
            state,
            "quiz_generator",
            {
                "prompt_input": prompt_input,
                "raw_llm_output": result.content,
                "llm_model_used": result.model or llm_settings.llm_model,
                "token_usage": result.token_usage,
                "qc_retry_mode": retry_mode,
                "gen_attempt": gen_attempt,
                "terminal_llm_failure": True,
            },
        )
        return failure

    raw = result.content or ""
    try:
        items = parse_json_array(raw, expected_count=state["question_count"])
        parsed, hints_stale_ids = normalize_parsed_items(items)
    except Exception as exc:  # noqa: BLE001
        error_return = {
            "error": f"Malformed quiz output: {exc}",
            "raw_llm_output": raw,
            "llm_model_used": result.model or llm_settings.llm_model,
            "token_usage": result.token_usage,
        }
        log_quiz_artifact(
            state,
            "quiz_generator",
            {
                "prompt_input": prompt_input,
                "raw_llm_output": raw,
                "llm_model_used": result.model or llm_settings.llm_model,
                "token_usage": result.token_usage,
                "qc_retry_mode": retry_mode,
                "gen_attempt": gen_attempt,
                "error": error_return["error"],
            },
        )
        return error_return

    if (
        retry_mode == "full_regeneration"
        and previous_questions
        and rewrite_question_ids
    ):
        # Preserve passing questions; only replace those flagged for reverify.
        parsed = merge_full_regeneration_preserving_passing(
            parsed,
            previous_questions,
            rewrite_question_ids=rewrite_question_ids,
        )

    success_return = {
        "prompt_input": prompt_input,
        "raw_llm_output": raw,
        "parsed_questions": parsed,
        "hints_stale_question_ids": hints_stale_ids,
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
        "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
        "fixed_questions": None,
    }
    log_quiz_artifact(
        state,
        "quiz_generator",
        {
            "prompt_input": prompt_input,
            "raw_llm_output": raw,
            "parsed_questions": parsed,
            "llm_model_used": success_return["llm_model_used"],
            "token_usage": result.token_usage,
            "qc_retry_mode": retry_mode,
            "gen_attempt": gen_attempt,
        },
    )
    return success_return
