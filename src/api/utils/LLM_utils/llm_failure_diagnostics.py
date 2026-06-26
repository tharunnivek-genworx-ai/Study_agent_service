"""Helpers for structured LLM failure payloads stored in qc_result JSONB."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
    HintGenerationDiagnosticsOut,
    QcInfraErrorType,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult

STUDY_LLM_FAILURE_PLACEHOLDER = (
    "## Generation unavailable\n\n"
    "Study material could not be generated because the AI service is temporarily "
    "unavailable. Please try again later."
)


def _serialize_provider_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return None
    raw_next = meta.get("next_llm_retry_at") or meta.get("nextLlmRetryAt")
    return {
        "apiKeyAlias": meta.get("api_key_alias") or meta.get("apiKeyAlias"),
        "attemptIndex": meta.get("attempt_index") or meta.get("attemptIndex"),
        "graphNode": meta.get("graph_node") or meta.get("graphNode"),
        "retryAfterSeconds": meta.get("retry_after_seconds")
        or meta.get("retryAfterSeconds"),
        "nextLlmRetryAt": _serialize_datetime(raw_next),
    }


def _serialize_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _dump_generation_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a JSONB-safe dict (no datetime/UUID objects)."""
    return GenerationDiagnosticsOut.model_validate(payload).model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )


def build_llm_failure_qc_result(result: GroqCallResult) -> dict[str, Any]:
    """Build a qc_result dict for terminal LLM failures (generator nodes)."""
    provider_meta = _serialize_provider_meta(result.provider_meta)
    if provider_meta and result.next_llm_retry_at is not None:
        provider_meta["nextLlmRetryAt"] = _serialize_datetime(result.next_llm_retry_at)

    payload: dict[str, Any] = {
        "errorType": result.error_type,
        "suggestion": result.suggestion,
        "providerMeta": provider_meta,
        "retryAfterSeconds": result.retry_after_seconds,
        "nextLlmRetryAt": _serialize_datetime(result.next_llm_retry_at),
    }
    return _dump_generation_diagnostics(payload)


def build_hint_invoke_failure_diagnostics(result: GroqCallResult) -> dict[str, Any]:
    """Build hintGeneration diagnostics for terminal hint LLM failures."""
    return HintGenerationDiagnosticsOut.model_validate(
        {
            "errorType": result.error_type,
            "retryAfterSeconds": result.retry_after_seconds,
            "nextLlmRetryAt": _serialize_datetime(result.next_llm_retry_at),
            "questionErrors": [],
        }
    ).model_dump(by_alias=True, exclude_none=True, mode="json")


def build_qc_infra_error_result(
    *,
    provider_meta: dict[str, Any] | None = None,
    retry_after_seconds: int | None = None,
    next_llm_retry_at: datetime | None = None,
    error_type: QcInfraErrorType = "llm_infra_error",
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Build a fail-open QC infra error payload (content saved, QC could not run)."""
    serialized_meta = _serialize_provider_meta(provider_meta)
    if serialized_meta and next_llm_retry_at is not None:
        serialized_meta["nextLlmRetryAt"] = _serialize_datetime(next_llm_retry_at)

    payload: dict[str, Any] = {
        "qcInfraError": True,
        "errorType": error_type,
        "providerMeta": serialized_meta,
        "suggestion": suggestion,
        "retryAfterSeconds": retry_after_seconds,
        "nextLlmRetryAt": _serialize_datetime(next_llm_retry_at),
    }
    return _dump_generation_diagnostics(payload)
