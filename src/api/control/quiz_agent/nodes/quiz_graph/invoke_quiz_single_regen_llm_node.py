"""Invoke the LLM for single-question mentor rework.

Graph node (rework subgraph)
----------------------------
Calls Groq with ``prompt_input`` from the prior node. On success sets
``raw_llm_output`` for parsing; on failure sets ``terminal_llm_failure`` or
``error``.

Routing: failure → END; success → ``parse_quiz_single_regen_output``.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from src.api.config import llm_settings
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.graph.node_helpers import (
    call_quiz_llm,
    log_quiz_artifact,
)

logger = logging.getLogger(__name__)


async def invoke_quiz_single_regen_llm(
    state: QuizGraphState,
) -> dict[str, Any]:
    """Invoke the LLM to produce patched questions for mentor-requested rework."""
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {
            **state,
            "error": "Missing prompt input for quiz single-question regen.",
        }

    result = await call_quiz_llm(
        system_prompt=prompt_input["system_prompt"],
        user_message=prompt_input["user_message"],
    )
    if not result.ok:
        logger.error("Groq quiz single-question regen failed: %s", result.error_type)
        failure = {
            **state,
            "terminal_llm_failure": True,
            "llm_error_type": result.error_type,
            "provider_meta": result.provider_meta,
            "next_llm_retry_at": result.next_llm_retry_at,
            "raw_llm_output": result.content,
            "llm_model_used": result.model or llm_settings.llm_model,
            "token_usage": result.token_usage,
        }
        log_quiz_artifact(
            cast(Any, state),
            "quiz_single_regen_llm",
            {
                "prompt_input": prompt_input,
                "raw_llm_output": result.content,
                "terminal_llm_failure": True,
            },
        )
        return failure

    llm_return = {
        **state,
        "raw_llm_output": result.content or "",
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
        "terminal_llm_failure": False,
    }
    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_llm",
        {
            "prompt_input": prompt_input,
            "raw_llm_output": result.content,
            "llm_model_used": llm_return.get("llm_model_used"),
            "token_usage": llm_return.get("token_usage"),
        },
    )
    return llm_return
