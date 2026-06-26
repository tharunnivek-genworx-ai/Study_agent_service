"""LLM verification pass with JSON parse retry and Groq key-rotation diagnostics."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.utils.LLM_utils.groq_retry import GroqCallResult
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_VERIFICATION_PARSE_RETRIES,
)
from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
    parse_qc_verification_response,
)

logger = logging.getLogger(__name__)


def _apply_groq_result_to_meta(
    meta: dict[str, Any],
    result: GroqCallResult,
    *,
    model_setting: str,
) -> None:
    meta.update(
        {
            "llm_ok": result.ok,
            "llm_error_type": result.error_type,
            "llm_model_used": result.model or model_setting,
            "raw_response": result.content,
            "provider_meta": result.provider_meta,
            "retry_after_seconds": result.retry_after_seconds,
            "next_llm_retry_at": result.next_llm_retry_at,
            "suggestion": result.suggestion,
        }
    )


async def run_llm_verification_pass(
    *,
    build_user_message: Any,
    system_prompt: str,
    reprompt_system: str,
    call_llm: Any,
    graph_node: str,
    model_setting: str,
    user_message_kwargs: dict[str, Any],
    pass_label: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Call an LLM verifier with Groq key rotation and one JSON-reprompt retry."""
    meta: dict[str, Any] = {
        "llm_ok": False,
        "llm_error_type": None,
        "llm_model_used": model_setting,
        "raw_response": None,
        "parse_ok": False,
        "retry_strategy": graph_node,
        "parse_retries": 0,
        "skipped": False,
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

    llm_result = await call_llm(messages=messages, graph_node=graph_node)
    _apply_groq_result_to_meta(meta, llm_result, model_setting=model_setting)

    if not llm_result.ok:
        logger.error(
            "%s LLM call failed (%s, node=%s)",
            pass_label,
            llm_result.error_type,
            graph_node,
        )
        return None, meta

    parsed = parse_qc_verification_response(llm_result.content or "", pass_label)
    if parsed is not None:
        meta["parse_ok"] = True
        return parsed, meta

    for attempt in range(MAX_VERIFICATION_PARSE_RETRIES):
        logger.warning(
            "%s JSON parse failed — reprompting (attempt %d)", pass_label, attempt + 1
        )
        meta["parse_retries"] = attempt + 1
        reprompt_messages = [
            SystemMessage(content=reprompt_system),
            HumanMessage(
                content=(
                    "Your previous response was not valid JSON. "
                    f"Return ONLY the verification JSON object for this {pass_label}.\n\n"
                    f"{user_message}"
                )
            ),
        ]
        llm_result = await call_llm(messages=reprompt_messages, graph_node=graph_node)
        _apply_groq_result_to_meta(meta, llm_result, model_setting=model_setting)
        if not llm_result.ok:
            return None, meta
        parsed = parse_qc_verification_response(
            llm_result.content or "", f"{pass_label} reprompt"
        )
        if parsed is not None:
            meta["parse_ok"] = True
            return parsed, meta

    logger.warning("%s JSON parse failed after reprompt", pass_label)
    return None, meta
