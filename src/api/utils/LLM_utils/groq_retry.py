# study_agent_service/src/api/utils/LLM_utils/groq_retry.py
"""Shared Groq LLM invocation with API-key rotation and structured failure results."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq

from src.api.config import llm_settings
from src.api.utils.LLM_utils.groq_key_pool import get_shared_key_pool

logger = logging.getLogger(__name__)

_BASE_DELAY_SECONDS = 1.0

_TOKEN_LIMIT_SUGGESTIONS: dict[str, str] = {
    "concept_checklist": (
        "Shorten teaching instruction or reduce reference PDF scope for checklist planning."
    ),
    "study_generator": (
        "Reduce reference PDF scope, shorten teaching instruction, or lower context size."
    ),
    "quiz_generator": "Reduce question_count or shorten study material.",
    "hint_generator": "Reduce active question count or use per-question regenerate.",
    "quality_check": "Shorten generated content sent to QC or reduce reference scope.",
    "qc_verification": "Shorten generated content sent to QC or reduce reference scope.",
    "qc_retry_verification": "Shorten revised sections or reduce document context size for QC.",
}

_DEFAULT_TOKEN_LIMIT_SUGGESTION = (
    "Reduce input size or shorten the content sent to the model."
)


@dataclass
class GroqCallResult:
    """Result of ``call_groq_with_rotation``."""

    ok: bool
    content: str | None = None
    error_type: str | None = None
    provider_meta: dict[str, Any] | None = None
    suggestion: str | None = None
    retry_after_seconds: int | None = None
    next_llm_retry_at: datetime | None = None
    token_usage: int | None = None
    model: str | None = None
    graph_node: str | None = field(default=None, repr=False)


def _flatten_content(content: Any) -> str:  # noqa: ANN401
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def _extract_token_usage(response: Any) -> int | None:  # noqa: ANN401
    usage = getattr(response, "usage_metadata", None)
    if usage and usage.get("total_tokens") is not None:
        return int(usage["total_tokens"])
    meta = getattr(response, "response_metadata", None) or {}
    token_meta = meta.get("token_usage") or {}
    total = token_meta.get("total_tokens")
    return int(total) if total is not None else None


def _extract_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    body = str(exc).lower()
    if "401" in body or "unauthorized" in body:
        return 401
    if "403" in body or "forbidden" in body:
        return 403
    if "429" in body or "rate limit" in body or "ratelimit" in body:
        return 429
    match = re.search(r"\b5\d{2}\b", body)
    if match:
        return int(match.group())
    return None


def _extract_retry_after_seconds(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is not None:
            try:
                return max(1, int(raw))
            except (TypeError, ValueError):
                pass
    return 60


def _is_timeout_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "timeout" in name
        or "timed out" in msg
        or "timeout" in msg
        or "readtimeout" in name
    )


def _is_token_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    patterns = (
        "token limit",
        "context length",
        "context_length",
        "maximum context",
        "max tokens",
        "too many tokens",
        "request too large",
        "payload too large",
    )
    return any(p in msg for p in patterns)


def _is_infra_error(exc: Exception) -> bool:
    if _is_timeout_error(exc):
        return True
    code = _extract_status_code(exc)
    return code is not None and code >= 500


def _token_limit_suggestion(graph_node: str | None) -> str:
    if graph_node and graph_node in _TOKEN_LIMIT_SUGGESTIONS:
        return _TOKEN_LIMIT_SUGGESTIONS[graph_node]
    return _DEFAULT_TOKEN_LIMIT_SUGGESTION


def _build_provider_meta(
    *,
    api_key_alias: str,
    attempt_index: int,
    graph_node: str | None,
    retry_after_seconds: int | None = None,
    next_llm_retry_at: datetime | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "api_key_alias": api_key_alias,
        "attempt_index": attempt_index,
        "graph_node": graph_node,
    }
    if retry_after_seconds is not None:
        meta["retry_after_seconds"] = retry_after_seconds
    if next_llm_retry_at is not None:
        meta["next_llm_retry_at"] = next_llm_retry_at
    return meta


def _failure_result(
    *,
    error_type: str,
    graph_node: str | None,
    model: str,
    provider_meta: dict[str, Any] | None = None,
    suggestion: str | None = None,
    retry_after_seconds: int | None = None,
    next_llm_retry_at: datetime | None = None,
) -> GroqCallResult:
    return GroqCallResult(
        ok=False,
        error_type=error_type,
        provider_meta=provider_meta,
        suggestion=suggestion,
        retry_after_seconds=retry_after_seconds,
        next_llm_retry_at=next_llm_retry_at,
        model=model,
        graph_node=graph_node,
    )


def _resolve_groq_sampling(
    *,
    temperature: float,
    top_p: float | None,
    do_sample: bool | None,
) -> tuple[float, float | None]:
    """Map do_sample intent to Groq temperature/top_p (Groq has no do_sample flag)."""
    if do_sample is False:
        return 0.0, 1.0
    if do_sample is True and top_p is None:
        return temperature, None
    return temperature, top_p


async def call_groq_with_rotation(
    *,
    messages: list[BaseMessage],
    model: str,
    temperature: float = 0.4,
    top_p: float | None = None,
    do_sample: bool | None = None,
    timeout: int = 120,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    graph_node: str | None = None,
) -> GroqCallResult:
    """Invoke ChatGroq with key rotation and structured terminal failures."""
    temperature, top_p = _resolve_groq_sampling(
        temperature=temperature,
        top_p=top_p,
        do_sample=do_sample,
    )
    pool = get_shared_key_pool()
    max_infra_attempts = llm_settings.llm_retry_attempts

    while True:
        key_pair = await pool.acquire_healthy_key()
        if key_pair is None:
            if await pool.all_blocked():
                return _failure_result(
                    error_type="llm_key_pool_exhausted",
                    graph_node=graph_node,
                    model=model,
                    provider_meta=_build_provider_meta(
                        api_key_alias="pool",
                        attempt_index=0,
                        graph_node=graph_node,
                    ),
                )
            retry_at = await pool.earliest_rate_limit_retry_at()
            retry_seconds = None
            if retry_at is not None:
                delta = retry_at - datetime.now(UTC)
                retry_seconds = max(1, int(delta.total_seconds()))
            return _failure_result(
                error_type="rate_limited",
                graph_node=graph_node,
                model=model,
                retry_after_seconds=retry_seconds,
                next_llm_retry_at=retry_at,
                provider_meta=_build_provider_meta(
                    api_key_alias="pool",
                    attempt_index=0,
                    graph_node=graph_node,
                    retry_after_seconds=retry_seconds,
                    next_llm_retry_at=retry_at,
                ),
            )

        alias, api_key = key_pair
        groq_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
            "timeout": timeout,
        }
        if top_p is not None:
            groq_kwargs["top_p"] = top_p
        if max_tokens is not None:
            groq_kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            groq_kwargs["response_format"] = response_format
        llm = ChatGroq(**groq_kwargs)

        for attempt in range(max_infra_attempts):
            try:
                response = await llm.ainvoke(messages)
                content = _flatten_content(response.content)
                return GroqCallResult(
                    ok=True,
                    content=content,
                    model=model,
                    token_usage=_extract_token_usage(response),
                    graph_node=graph_node,
                    provider_meta=_build_provider_meta(
                        api_key_alias=alias,
                        attempt_index=attempt + 1,
                        graph_node=graph_node,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Groq call failed (key=%s, attempt=%d/%d, node=%s): %s",
                    alias,
                    attempt + 1,
                    max_infra_attempts,
                    graph_node,
                    exc,
                )

                if _is_token_limit_error(exc):
                    return _failure_result(
                        error_type="token_limit",
                        graph_node=graph_node,
                        model=model,
                        provider_meta=_build_provider_meta(
                            api_key_alias=alias,
                            attempt_index=attempt + 1,
                            graph_node=graph_node,
                        ),
                        suggestion=_token_limit_suggestion(graph_node),
                    )

                status = _extract_status_code(exc)

                if status in (401, 403):
                    await pool.mark_blocked(alias)
                    break

                if status == 429:
                    retry_seconds = _extract_retry_after_seconds(exc)
                    until = datetime.now(UTC) + timedelta(seconds=retry_seconds)
                    await pool.mark_rate_limited(alias, until)
                    break

                if _is_infra_error(exc):
                    if attempt < max_infra_attempts - 1:
                        await asyncio.sleep(_BASE_DELAY_SECONDS * (2**attempt))
                        continue
                    return _failure_result(
                        error_type="llm_infra_error",
                        graph_node=graph_node,
                        model=model,
                        provider_meta=_build_provider_meta(
                            api_key_alias=alias,
                            attempt_index=attempt + 1,
                            graph_node=graph_node,
                        ),
                    )

                return _failure_result(
                    error_type="llm_infra_error",
                    graph_node=graph_node,
                    model=model,
                    provider_meta=_build_provider_meta(
                        api_key_alias=alias,
                        attempt_index=attempt + 1,
                        graph_node=graph_node,
                    ),
                )
