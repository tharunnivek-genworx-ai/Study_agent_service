"""QC infrastructure failure state returns — never fake-pass."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from src.api.config import llm_settings
from src.api.schemas.common import QcInfraErrorType
from src.api.utils.LLM_utils.groq_retry import GroqCallResult
from src.api.utils.LLM_utils.llm_failure_diagnostics import build_qc_infra_error_result
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_QC_ATTEMPTS,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.result_builder import (
    qc_models_used,
)

_GROQ_QC_INFRA_ERRORS: frozenset[str] = frozenset(
    {
        "rate_limited",
        "token_limit",
        "llm_infra_error",
        "llm_key_pool_exhausted",
    }
)


def resolve_qc_infra_error_type(error_type: str | None) -> QcInfraErrorType:
    """Map a Groq failure type to a QC infra error type."""
    if error_type in _GROQ_QC_INFRA_ERRORS:
        return cast(QcInfraErrorType, error_type)
    return "qc_verification_failed"


def build_infra_failure_return(
    *,
    new_attempt: int,
    error_type: QcInfraErrorType | str = "qc_verification_failed",
    extraction_snapshot: dict[str, Any] | None,
    provider_meta: dict[str, Any] | None = None,
    retry_after_seconds: int | None = None,
    next_llm_retry_at: datetime | None = None,
    suggestion: str | None = None,
    groq_result: GroqCallResult | None = None,
) -> dict[str, Any]:
    """Return state for QC infrastructure failure — never fake-pass."""
    if groq_result is not None and not groq_result.ok:
        error_type = resolve_qc_infra_error_type(groq_result.error_type)
        provider_meta = groq_result.provider_meta
        retry_after_seconds = groq_result.retry_after_seconds
        next_llm_retry_at = groq_result.next_llm_retry_at
        suggestion = groq_result.suggestion

    permanently_failed = new_attempt >= MAX_QC_ATTEMPTS
    infra_result = build_qc_infra_error_result(
        error_type=cast(QcInfraErrorType, error_type),
        provider_meta=provider_meta,
        retry_after_seconds=retry_after_seconds,
        next_llm_retry_at=next_llm_retry_at,
        suggestion=suggestion,
    )
    return {
        "qc_passed": False,
        "qc_result": infra_result,
        "qc_feedback": "",
        "qc_attempt": new_attempt,
        "qc_failed_permanently": permanently_failed,
        "qc_extraction": extraction_snapshot,
        "qc_llm_model_used": llm_settings.qc_llm_model,
        "qc_llm_models_used": qc_models_used(llm_settings.qc_llm_model, None),
        "llm_error_type": str(error_type),
        "provider_meta": provider_meta,
        "next_llm_retry_at": next_llm_retry_at,
    }
