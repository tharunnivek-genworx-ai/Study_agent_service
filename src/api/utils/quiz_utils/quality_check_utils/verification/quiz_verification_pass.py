"""Groq Llama 70B quiz QC verification — single pass with JSON mode."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config import llm_settings
from src.api.utils.LLM_utils.groq_quiz_qc_client import call_groq_quiz_qc_verification
from src.api.utils.quiz_utils.quality_check_utils.parsing.json_parse import (
    parse_quiz_qc_response,
)

logger = logging.getLogger(__name__)


async def run_quiz_verification_pass(
    *,
    build_user_message: Any,
    system_prompt: str,
    user_message_kwargs: dict[str, Any],
    question_count: int,
    graph_node: str = "quality_check",
    pass_label: str = "Quiz QC",
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Single quiz QC LLM call with JSON mode — no reprompt on parse failure."""
    meta: dict[str, Any] = {
        "llm_ok": False,
        "llm_error_type": None,
        "llm_model_used": llm_settings.qc_llm_model,
        "raw_response": None,
        "parse_ok": False,
        "parse_retries": 0,
        "provider_meta": None,
        "retry_after_seconds": None,
        "next_llm_retry_at": None,
        "suggestion": None,
    }

    user_message = build_user_message(**user_message_kwargs)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    llm_result = await call_groq_quiz_qc_verification(
        messages=messages,
        graph_node=graph_node,
        question_count=question_count,
    )
    meta.update(
        {
            "llm_ok": llm_result.ok,
            "llm_error_type": llm_result.error_type,
            "llm_model_used": llm_result.model or llm_settings.qc_llm_model,
            "raw_response": llm_result.content,
            "provider_meta": llm_result.provider_meta,
            "retry_after_seconds": llm_result.retry_after_seconds,
            "next_llm_retry_at": llm_result.next_llm_retry_at,
            "suggestion": llm_result.suggestion,
        }
    )

    if not llm_result.ok:
        logger.error(
            "%s LLM call failed (%s)",
            pass_label,
            llm_result.error_type,
        )
        return None, meta

    parsed = parse_quiz_qc_response(
        llm_result.content or "", pass_label, question_count=question_count
    )
    if parsed is not None:
        meta["parse_ok"] = True
        return parsed, meta

    logger.warning("%s JSON parse/validation failed on single pass", pass_label)
    return None, meta
