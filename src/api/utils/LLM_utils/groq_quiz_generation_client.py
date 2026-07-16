"""Groq quiz generation — JSON mode with TPM-aware, question-scaled max_tokens."""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from src.api.config import llm_settings
from src.api.utils.LLM_utils.groq_qc_client import (
    _QC_COMPLETION_FLOOR,
    _QC_TPM_INPUT_BUFFER,
    _estimate_input_tokens,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation


def _estimate_quiz_generation_output_tokens(question_count: int) -> int:
    """Rough completion budget: ~500 tokens per question + wrapper overhead."""
    per_question = 500
    overhead = 400
    return overhead + per_question * max(question_count, 1)


def _effective_quiz_generation_max_tokens(
    messages: list[BaseMessage],
    question_count: int,
) -> int:
    """Stay under Groq TPM while allowing enough room for large quizzes."""
    ceiling = llm_settings.quiz_generation_llm_max_tokens
    tpm_limit = llm_settings.groq_qc_tpm_limit
    desired = _estimate_quiz_generation_output_tokens(question_count)
    if tpm_limit <= 0:
        return max(_QC_COMPLETION_FLOOR, min(ceiling, desired))

    estimated_input = _estimate_input_tokens(messages)
    available = tpm_limit - estimated_input - _QC_TPM_INPUT_BUFFER
    if available < _QC_COMPLETION_FLOOR:
        return _QC_COMPLETION_FLOOR
    return max(_QC_COMPLETION_FLOOR, min(ceiling, available, desired))


async def call_groq_quiz_generation(
    *,
    messages: list[BaseMessage],
    question_count: int,
    graph_node: str = "quiz_generator",
) -> GroqCallResult:
    """Quiz generation — Groq with key rotation, JSON object output, scaled max_tokens."""
    model = llm_settings.llm_model
    max_tokens = _effective_quiz_generation_max_tokens(messages, question_count)
    return await call_groq_with_rotation(
        messages=messages,
        model=model,
        temperature=llm_settings.quiz_generation_temperature,
        timeout=120,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        graph_node=graph_node,
    )
