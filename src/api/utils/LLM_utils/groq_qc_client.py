# src/api/utils/LLM_utils/groq_qc_client.py
"""Groq-hosted LLM client for unified QC verification with shared key rotation."""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from src.api.config.llm_config import llm_settings
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation

_QC_COMPLETION_FLOOR = 1024
_QC_TPM_INPUT_BUFFER = 256


def _message_char_count(messages: list[BaseMessage]) -> int:
    total = 0
    for message in messages:
        content = message.content
        if isinstance(content, str):
            total += len(content)
        else:
            total += len(str(content))
    return total


def _estimate_input_tokens(messages: list[BaseMessage]) -> int:
    """Rough token estimate for Groq TPM budgeting (chars / 4)."""
    return max(1, _message_char_count(messages) // 4)


def _effective_qc_max_tokens(messages: list[BaseMessage]) -> int:
    """Stay under Groq per-request TPM without truncating the document payload."""
    ceiling = llm_settings.qc_llm_max_tokens
    tpm_limit = llm_settings.groq_qc_tpm_limit
    if tpm_limit <= 0:
        return ceiling

    estimated_input = _estimate_input_tokens(messages)
    available = tpm_limit - estimated_input - _QC_TPM_INPUT_BUFFER
    if available < _QC_COMPLETION_FLOOR:
        return _QC_COMPLETION_FLOOR
    return min(ceiling, available)


async def call_groq_qc_verification(
    *,
    messages: list[BaseMessage],
    graph_node: str | None = "qc_verification",
) -> GroqCallResult:
    """Unified QC pass — Groq with key rotation, JSON output, and zero temperature."""
    model = llm_settings.qc_llm_model
    max_tokens = _effective_qc_max_tokens(messages)
    return await call_groq_with_rotation(
        messages=messages,
        model=model,
        temperature=0,
        timeout=180,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        graph_node=graph_node,
    )
