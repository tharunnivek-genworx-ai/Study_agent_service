"""Project QC diagnostics in API responses for demo-safe frontend display.

When ``suppress_expected_qc_failures_from_frontend`` is enabled, expected
content/deterministic permanent QC failures are redacted on read while
operational failures (infra, rate limits, generator errors) remain visible.
DB persistence and graph routing are unchanged.
"""

from __future__ import annotations

from typing import Any

from src.api.config.feature_config import feature_settings
from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
)
from src.api.schemas.quiz_schemas.quiz_schema import QuizOut
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialFeedbackResponse,
    StudyMaterialVersionOut,
)

QcResultLike = GenerationDiagnosticsOut | dict[str, Any] | None


def is_operational_qc_failure(qc_result: QcResultLike) -> bool:
    """Return True when QC diagnostics indicate an operational/infra failure.

    Operational failures must remain visible in the frontend (rate limits,
    token limits, LLM infra, key pool exhaustion, QC extraction/verification
    crashes, and terminal generator failures surfaced via ``errorType``).
    """
    if qc_result is None:
        return False
    if isinstance(qc_result, GenerationDiagnosticsOut):
        if qc_result.qc_infra_error is True:
            return True
        return bool(qc_result.error_type)
    if qc_result.get("qcInfraError") is True or qc_result.get("qc_infra_error") is True:
        return True
    error_type = qc_result.get("errorType") or qc_result.get("error_type")
    return bool(error_type)


def should_suppress_expected_qc_for_frontend(
    qc_failed_permanently: bool,
    qc_result: QcResultLike,
) -> bool:
    """Return True when expected permanent QC failure fields should be cleared."""
    if not feature_settings.suppress_expected_qc_failures_from_frontend:
        return False
    if not qc_failed_permanently:
        return False
    return not is_operational_qc_failure(qc_result)


def project_qc_fields_for_frontend(
    qc_failed_permanently: bool,
    qc_result: QcResultLike,
) -> tuple[bool, QcResultLike]:
    """Return projected ``(qc_failed_permanently, qc_result)`` for API responses."""
    if should_suppress_expected_qc_for_frontend(qc_failed_permanently, qc_result):
        return False, None
    return qc_failed_permanently, qc_result


def project_study_material_version_out(
    out: StudyMaterialVersionOut,
) -> StudyMaterialVersionOut:
    """Apply QC field projection to a study material version response."""
    if not should_suppress_expected_qc_for_frontend(
        out.qc_failed_permanently,
        out.qc_result,
    ):
        return out
    updates: dict[str, Any] = {
        "qc_failed_permanently": False,
        "qc_result": None,
    }
    if out.generation_outcome == "qc_failed":
        updates["generation_outcome"] = "deliverable"
    return out.model_copy(update=updates)


def project_study_material_feedback_response(
    out: StudyMaterialFeedbackResponse,
) -> StudyMaterialFeedbackResponse:
    """Project top-level and nested ``new_version`` QC fields for feedback responses."""
    projected_failed, projected_result = project_qc_fields_for_frontend(
        out.qc_failed_permanently,
        out.qc_result,
    )
    new_version = out.new_version
    if new_version is not None:
        new_version = project_study_material_version_out(new_version)

    if (
        projected_failed == out.qc_failed_permanently
        and projected_result is out.qc_result
        and new_version is out.new_version
    ):
        return out

    return out.model_copy(
        update={
            "qc_failed_permanently": projected_failed,
            "qc_result": projected_result,
            "new_version": new_version,
        }
    )


def project_quiz_out(out: QuizOut) -> QuizOut:
    """Apply QC field projection to a quiz response."""
    projected_failed, projected_result = project_qc_fields_for_frontend(
        out.qc_failed_permanently,
        out.qc_result,
    )
    if (
        projected_failed == out.qc_failed_permanently
        and projected_result is out.qc_result
    ):
        return out
    return out.model_copy(
        update={
            "qc_failed_permanently": projected_failed,
            "qc_result": projected_result,
        }
    )


def _project_qc_fields_in_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Project QC fields inside a serialized response dict."""
    qc_failed = bool(payload.get("qc_failed_permanently"))
    qc_result = payload.get("qc_result")
    if not should_suppress_expected_qc_for_frontend(qc_failed, qc_result):
        return payload

    result = dict(payload)
    result["qc_failed_permanently"] = False
    result["qc_result"] = None
    if payload.get("generation_outcome") == "qc_failed":
        result["generation_outcome"] = "deliverable"
    return result


def _project_study_material_feedback_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Project QC fields in a stored study-material feedback result dict."""
    result = _project_qc_fields_in_dict(payload)
    new_version = payload.get("new_version")
    if isinstance(new_version, dict):
        result["new_version"] = _project_qc_fields_in_dict(new_version)
    return result


def project_generation_run_result_payload(stored: dict[str, Any]) -> dict[str, Any]:
    """Project QC fields in nested generation-run result payloads (read-time).

    Covers ``study_material_generate``, ``study_material_feedback``, and ``quiz``
    blobs stored in ``request_params.result``. Idempotent when builders already
    redacted at write time.
    """
    if not stored:
        return stored
    if not feature_settings.suppress_expected_qc_failures_from_frontend:
        return stored

    result = dict(stored)

    study_material_generate = stored.get("study_material_generate")
    if isinstance(study_material_generate, dict):
        result["study_material_generate"] = _project_qc_fields_in_dict(
            study_material_generate
        )

    study_material_feedback = stored.get("study_material_feedback")
    if isinstance(study_material_feedback, dict):
        result["study_material_feedback"] = _project_study_material_feedback_dict(
            study_material_feedback
        )

    quiz = stored.get("quiz")
    if isinstance(quiz, dict):
        result["quiz"] = _project_qc_fields_in_dict(quiz)

    return result
