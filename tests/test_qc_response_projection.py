"""Unit tests for demo-safe QC field projection in API responses."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.config.feature_config import feature_settings
from src.api.core.services.generation_run_service import GenerationRunService
from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
)
from src.api.schemas.quiz_schemas.quiz_schema import QuizOut
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialFeedbackResponse,
    StudyMaterialVersionOut,
)
from src.api.utils.qc_response_projection import (
    is_operational_qc_failure,
    project_generation_run_result_payload,
    project_qc_fields_for_frontend,
    project_quiz_out,
    project_study_material_feedback_response,
    project_study_material_version_out,
    should_suppress_expected_qc_for_frontend,
)

_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

_EXPECTED_QC_RESULT = {
    "overall_status": "fail",
    "checks": [
        {
            "id": "mc_1",
            "category": "must_cover",
            "question": "Coverage?",
            "passed": False,
            "severity": "critical",
        }
    ],
}

_INFRA_QC_RESULT = {"qcInfraError": True, "errorType": "rate_limited"}

_GENERATOR_FAILURE_QC_RESULT = {"errorType": "token_limit_exceeded"}


@pytest.fixture
def suppress_qc_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feature_settings,
        "suppress_expected_qc_failures_from_frontend",
        True,
    )


@pytest.fixture
def suppress_qc_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feature_settings,
        "suppress_expected_qc_failures_from_frontend",
        False,
    )


def _study_material_version_out(**overrides: object) -> StudyMaterialVersionOut:
    defaults: dict[str, object] = {
        "version_id": uuid4(),
        "node_id": uuid4(),
        "space_id": uuid4(),
        "version_number": 1,
        "content": "Full study material body.",
        "generation_type": "generate",
        "mentor_feedback_used": None,
        "reference_material_id": None,
        "based_on_version_id": None,
        "llm_model_used": None,
        "prompt_snapshot": None,
        "token_usage": None,
        "is_active": True,
        "is_published": False,
        "published_at": None,
        "published_by": None,
        "created_by": uuid4(),
        "created_at": _NOW,
        "qc_failed_permanently": True,
        "qc_result": GenerationDiagnosticsOut.model_validate(_EXPECTED_QC_RESULT),
        "generation_outcome": "qc_failed",
    }
    defaults.update(overrides)
    return StudyMaterialVersionOut.model_validate(defaults)


def _quiz_out(**overrides: object) -> QuizOut:
    defaults: dict[str, object] = {
        "quiz_id": uuid4(),
        "node_id": uuid4(),
        "space_id": uuid4(),
        "study_material_version_id": uuid4(),
        "title": "Quiz",
        "total_questions": 5,
        "difficulty": "medium",
        "is_published": False,
        "published_at": None,
        "pass_threshold_percent": 70,
        "created_by": uuid4(),
        "created_at": _NOW,
        "updated_at": _NOW,
        "qc_failed_permanently": True,
        "qc_result": GenerationDiagnosticsOut.model_validate(_EXPECTED_QC_RESULT),
    }
    defaults.update(overrides)
    return QuizOut.model_validate(defaults)


def test_is_operational_qc_failure_detects_infra_and_error_type() -> None:
    assert is_operational_qc_failure({"qcInfraError": True}) is True
    assert is_operational_qc_failure({"errorType": "rate_limited"}) is True
    assert is_operational_qc_failure({"qc_infra_error": True}) is True
    assert is_operational_qc_failure({"error_type": "token_limit_exceeded"}) is True
    assert (
        is_operational_qc_failure(GenerationDiagnosticsOut(error_type="rate_limited"))
        is True
    )
    assert is_operational_qc_failure(_EXPECTED_QC_RESULT) is False
    assert is_operational_qc_failure(None) is False


def test_should_suppress_when_flag_on_and_expected_failure(
    suppress_qc_on: None,
) -> None:
    assert should_suppress_expected_qc_for_frontend(True, _EXPECTED_QC_RESULT) is True
    assert should_suppress_expected_qc_for_frontend(True, _INFRA_QC_RESULT) is False
    assert (
        should_suppress_expected_qc_for_frontend(True, _GENERATOR_FAILURE_QC_RESULT)
        is False
    )
    assert should_suppress_expected_qc_for_frontend(True, None) is True


def test_should_suppress_never_when_flag_off(suppress_qc_off: None) -> None:
    assert should_suppress_expected_qc_for_frontend(False, _EXPECTED_QC_RESULT) is False
    assert should_suppress_expected_qc_for_frontend(True, _EXPECTED_QC_RESULT) is False


def test_project_qc_fields_flag_off_passthrough(suppress_qc_off: None) -> None:
    failed, result = project_qc_fields_for_frontend(True, _EXPECTED_QC_RESULT)
    assert failed is True
    assert result == _EXPECTED_QC_RESULT


def test_project_qc_fields_expected_failure_redacted(suppress_qc_on: None) -> None:
    failed, result = project_qc_fields_for_frontend(True, _EXPECTED_QC_RESULT)
    assert failed is False
    assert result is None


def test_project_qc_fields_operational_failure_preserved(suppress_qc_on: None) -> None:
    failed, result = project_qc_fields_for_frontend(True, _INFRA_QC_RESULT)
    assert failed is True
    assert result == _INFRA_QC_RESULT

    failed, result = project_qc_fields_for_frontend(True, _GENERATOR_FAILURE_QC_RESULT)
    assert failed is True
    assert result == _GENERATOR_FAILURE_QC_RESULT


def test_project_study_material_version_out_remaps_generation_outcome(
    suppress_qc_on: None,
) -> None:
    out = _study_material_version_out()
    projected = project_study_material_version_out(out)

    assert projected.qc_failed_permanently is False
    assert projected.qc_result is None
    assert projected.generation_outcome == "deliverable"
    assert projected.content == out.content


def test_project_study_material_version_out_success_unchanged(
    suppress_qc_on: None,
) -> None:
    out = _study_material_version_out(
        qc_failed_permanently=False,
        qc_result=GenerationDiagnosticsOut(overall_status="pass"),
        generation_outcome="deliverable",
    )
    projected = project_study_material_version_out(out)
    assert projected is out


def test_project_study_material_feedback_response_nested_and_top_level(
    suppress_qc_on: None,
) -> None:
    new_version = _study_material_version_out()
    feedback = StudyMaterialFeedbackResponse(
        has_new_version=True,
        new_version_id=new_version.version_id,
        status="ok",
        new_version=new_version,
        qc_failed_permanently=True,
        qc_result=GenerationDiagnosticsOut.model_validate(_EXPECTED_QC_RESULT),
    )

    projected = project_study_material_feedback_response(feedback)

    assert projected.qc_failed_permanently is False
    assert projected.qc_result is None
    assert projected.new_version is not None
    assert projected.new_version.qc_failed_permanently is False
    assert projected.new_version.qc_result is None
    assert projected.new_version.generation_outcome == "deliverable"


def test_project_quiz_out_expected_failure_redacted(suppress_qc_on: None) -> None:
    out = _quiz_out()
    projected = project_quiz_out(out)

    assert projected.qc_failed_permanently is False
    assert projected.qc_result is None
    assert projected.title == out.title


def test_project_generation_run_result_payload_nested_sections(
    suppress_qc_on: None,
) -> None:
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
            "generation_outcome": "qc_failed",
            "content": "generate body",
        },
        "study_material_feedback": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
            "new_version": {
                "qc_failed_permanently": True,
                "qc_result": _EXPECTED_QC_RESULT,
                "generation_outcome": "qc_failed",
                "content": "feedback body",
            },
        },
        "quiz": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
            "title": "Quiz title",
        },
    }

    projected = project_generation_run_result_payload(stored)

    assert projected["study_material_generate"]["qc_failed_permanently"] is False
    assert projected["study_material_generate"]["qc_result"] is None
    assert projected["study_material_generate"]["generation_outcome"] == "deliverable"
    assert projected["study_material_generate"]["content"] == "generate body"

    assert projected["study_material_feedback"]["qc_failed_permanently"] is False
    assert projected["study_material_feedback"]["qc_result"] is None
    nested = projected["study_material_feedback"]["new_version"]
    assert nested["qc_failed_permanently"] is False
    assert nested["qc_result"] is None
    assert nested["generation_outcome"] == "deliverable"

    assert projected["quiz"]["qc_failed_permanently"] is False
    assert projected["quiz"]["qc_result"] is None
    assert projected["quiz"]["title"] == "Quiz title"


def test_project_generation_run_result_payload_preserves_operational(
    suppress_qc_on: None,
) -> None:
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": True,
            "qc_result": _INFRA_QC_RESULT,
        },
        "quiz": {
            "qc_failed_permanently": True,
            "qc_result": _GENERATOR_FAILURE_QC_RESULT,
        },
    }

    projected = project_generation_run_result_payload(stored)

    assert projected["study_material_generate"]["qc_failed_permanently"] is True
    assert projected["study_material_generate"]["qc_result"] == _INFRA_QC_RESULT
    assert projected["quiz"]["qc_result"] == _GENERATOR_FAILURE_QC_RESULT


def test_project_generation_run_result_payload_flag_off_passthrough(
    suppress_qc_off: None,
) -> None:
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
        }
    }
    assert project_generation_run_result_payload(stored) == stored


def test_project_generation_run_result_payload_idempotent_when_already_redacted(
    suppress_qc_on: None,
) -> None:
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": False,
            "qc_result": None,
            "generation_outcome": "deliverable",
        }
    }
    assert project_generation_run_result_payload(stored) == stored


@pytest.mark.asyncio
async def test_get_run_result_applies_projection_on_read(suppress_qc_on: None) -> None:
    run_id = uuid4()
    mentor_id = uuid4()
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
            "generation_outcome": "qc_failed",
            "content": "full doc",
        },
        "quiz": {
            "qc_failed_permanently": True,
            "qc_result": _INFRA_QC_RESULT,
        },
    }
    run = SimpleNamespace(
        run_id=run_id,
        mentor_id=mentor_id,
        pipeline="study_material",
        status="completed",
        error_message=None,
        request_params={"result": stored},
    )

    session = MagicMock()
    service = GenerationRunService(session)
    service.repo = MagicMock()
    service.repo.get_by_id = AsyncMock(return_value=run)

    result = await service.get_run_result(run_id, mentor_id=mentor_id)

    assert result.study_material_generate is not None
    assert result.study_material_generate["qc_failed_permanently"] is False
    assert result.study_material_generate["qc_result"] is None
    assert result.study_material_generate["generation_outcome"] == "deliverable"
    assert result.study_material_generate["content"] == "full doc"

    assert result.quiz is not None
    assert result.quiz["qc_failed_permanently"] is True
    assert result.quiz["qc_result"] == _INFRA_QC_RESULT


@pytest.mark.asyncio
async def test_get_run_result_passthrough_when_flag_off(suppress_qc_off: None) -> None:
    run_id = uuid4()
    mentor_id = uuid4()
    stored = {
        "study_material_generate": {
            "qc_failed_permanently": True,
            "qc_result": _EXPECTED_QC_RESULT,
        }
    }
    run = SimpleNamespace(
        run_id=run_id,
        mentor_id=mentor_id,
        pipeline="study_material",
        status="completed",
        error_message=None,
        request_params={"result": stored},
    )

    session = MagicMock()
    service = GenerationRunService(session)
    service.repo = MagicMock()
    service.repo.get_by_id = AsyncMock(return_value=run)

    result = await service.get_run_result(run_id, mentor_id=mentor_id)

    assert result.study_material_generate == stored["study_material_generate"]
