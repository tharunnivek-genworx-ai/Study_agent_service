"""Shared Groq LLM invocation helper with API-key rotation on rate-limit errors.

Usage
-----
from src.api.utils.groq_retry import invoke_llm_rotating

raw, model, token_usage = await invoke_llm_rotating(
    messages=[SystemMessage(...), HumanMessage(...)],
    model=settings.llm_model,
    temperature=0.4,
    timeout=120,
)

The helper rotates through all configured GROQ API keys whenever a rate-limit
(HTTP 429 / RateLimitError) is encountered, giving each key one attempt before
moving on to the next.  Once all keys are exhausted it re-raises the last
exception.  Non-rate-limit errors are still retried with the same key up to
``extra_retries`` times with exponential back-off before the error is surfaced.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq

from src.api.config.dbconfig import settings

logger = logging.getLogger(__name__)

_BASE_DELAY_SECONDS = 1.0


def _get_api_keys() -> list[str]:
    """Return all configured, non-empty Groq API keys in rotation order."""
    candidates = [
        settings.groq_api_key,
        settings.groq_api_key_2,
        settings.groq_api_key_3,
        settings.groq_api_key_4,
    ]
    return [k for k in candidates if k]


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


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect Groq / HTTP 429 rate-limit errors heuristically."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "ratelimit" in name
        or "rate_limit" in name
        or "rate limit" in msg
        or "429" in msg
        or "quota" in msg
    )


async def invoke_llm_rotating(
    *,
    messages: list[BaseMessage],
    model: str,
    temperature: float = 0.4,
    timeout: int = 120,
    extra_retries: int = 1,
) -> tuple[str, str, int | None]:
    """Invoke a ChatGroq model, rotating API keys on rate-limit errors.

    Parameters
    ----------
    messages:
        The list of ``BaseMessage`` objects to send to the LLM.
    model:
        Groq model name (e.g. ``"llama-3.3-70b-versatile"``).
    temperature:
        Sampling temperature.
    timeout:
        HTTP request timeout in seconds.
    extra_retries:
        Number of additional attempts per key for *non-rate-limit* errors
        (each attempt is separated by exponential back-off).

    Returns
    -------
    tuple[str, str, int | None]
        ``(content, model_name, token_usage)``
    """
    keys = _get_api_keys()
    if not keys:
        raise RuntimeError(
            "No Groq API keys are configured. "
            "Set at least one of GROQ_API_KEY / GROQ_API_KEY_2 / "
            "GROQ_API_KEY_3 / GROQ_API_KEY_4 in your environment."
        )

    last_exc: Exception | None = None

    for key_index, api_key in enumerate(keys):
        groq_kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
            "timeout": timeout,
        }
        llm = ChatGroq(**groq_kwargs)

        for attempt in range(extra_retries + 1):
            try:
                response = await llm.ainvoke(messages)
                content = _flatten_content(response.content)
                return content, model, _extract_token_usage(response)

            except Exception as exc:  # noqa: BLE001
                last_exc = exc

                if _is_rate_limit_error(exc):
                    logger.warning(
                        "Rate-limit hit on key %d/%d (attempt %d): %s — rotating key.",
                        key_index + 1,
                        len(keys),
                        attempt + 1,
                        exc,
                    )
                    # Stop retrying this key and move to the next one.
                    break

                logger.warning(
                    "LLM attempt %d/%d on key %d/%d failed: %s",
                    attempt + 1,
                    extra_retries + 1,
                    key_index + 1,
                    len(keys),
                    exc,
                )
                if attempt < extra_retries:
                    await asyncio.sleep(_BASE_DELAY_SECONDS * (2**attempt))

    raise (
        last_exc
        if last_exc
        else RuntimeError("LLM invocation failed after all retries.")
    )
