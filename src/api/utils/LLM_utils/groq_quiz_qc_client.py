"""Groq QC verification for quiz generation — JSON mode, TPM-aware token budget."""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from src.api.config.llm_config import llm_settings
from src.api.utils.LLM_utils.groq_qc_client import (
    _QC_COMPLETION_FLOOR,
    _QC_TPM_INPUT_BUFFER,
    _estimate_input_tokens,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation


def _estimate_quiz_qc_output_tokens(question_count: int) -> int:
    """Rough completion budget: ~220 tokens per question (2 checks) + summary."""
    per_question = 220
    overhead = 600
    return overhead + per_question * max(question_count, 1)


def _effective_quiz_qc_max_tokens(messages: list[BaseMessage]) -> int:
    """Stay under Groq TPM while allowing a higher quiz-QC completion ceiling."""
    ceiling = llm_settings.quiz_qc_llm_max_tokens
    tpm_limit = llm_settings.groq_qc_tpm_limit
    if tpm_limit <= 0:
        return ceiling

    estimated_input = _estimate_input_tokens(messages)
    available = tpm_limit - estimated_input - _QC_TPM_INPUT_BUFFER
    if available < _QC_COMPLETION_FLOOR:
        return _QC_COMPLETION_FLOOR
    return min(ceiling, available)


async def call_groq_quiz_qc_verification(
    *,
    messages: list[BaseMessage],
    graph_node: str = "quality_check",
    question_count: int = 10,
) -> GroqCallResult:
    """Quiz QC pass — Groq with key rotation, JSON output, and scaled max_tokens."""
    model = llm_settings.qc_llm_model
    tpm_capped = _effective_quiz_qc_max_tokens(messages)
    desired = _estimate_quiz_qc_output_tokens(question_count)
    max_tokens = max(_QC_COMPLETION_FLOOR, min(tpm_capped, desired))
    return await call_groq_with_rotation(
        messages=messages,
        model=model,
        temperature=0,
        timeout=180,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        graph_node=graph_node,
    )
