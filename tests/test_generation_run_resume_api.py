"""Tests for generation run status and resume validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.core.services.generation_run_service import GenerationRunService
from src.api.schemas.generation_run_schema import (
    MAX_RESUME_ATTEMPTS,
    GenerationRunOut,
    GenerationRunStatus,
)


def _make_run(
    *,
    status: str = GenerationRunStatus.FAILED.value,
    attempt_count: int = 0,
    next_llm_retry_at: datetime | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        run_id=uuid4(),
        pipeline="study_material",
        resource_type="node",
        resource_id=uuid4(),
        node_id=uuid4(),
        space_id=uuid4(),
        mentor_id=uuid4(),
        status=status,
        last_completed_node="concept_checklist",
        generation_mode="generate",
        artifact_run_id=None,
        progress_step_index=1,
        error_message="LLM unavailable",
        error_type="terminal_llm_failure",
        next_llm_retry_at=next_llm_retry_at,
        attempt_count=attempt_count,
        request_params={},
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def test_generation_run_out_resumable_when_failed_and_cooldown_elapsed() -> None:
    run = _make_run()
    out = GenerationRunOut.from_orm_run(run)
    assert out.resumable is True
    assert out.seconds_until_retry is None


def test_generation_run_out_not_resumable_during_cooldown() -> None:
    retry_at = datetime.now(UTC) + timedelta(minutes=5)
    run = _make_run(next_llm_retry_at=retry_at)
    out = GenerationRunOut.from_orm_run(run)
    assert out.resumable is False
    assert out.seconds_until_retry is not None
    assert out.seconds_until_retry > 0


def test_generation_run_out_not_resumable_when_attempt_cap_reached() -> None:
    run = _make_run(attempt_count=MAX_RESUME_ATTEMPTS)
    out = GenerationRunOut.from_orm_run(run)
    assert out.resumable is False


def test_validate_resumable_rejects_cooldown() -> None:
    service = GenerationRunService(session=None)  # type: ignore[arg-type]
    retry_at = datetime.now(UTC) + timedelta(minutes=2)
    run = _make_run(next_llm_retry_at=retry_at)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_resumable(run, run_id=run.run_id)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


def test_validate_resumable_rejects_non_failed_status() -> None:
    service = GenerationRunService(session=None)  # type: ignore[arg-type]
    run = _make_run(status=GenerationRunStatus.RUNNING.value)

    with pytest.raises(HTTPException) as exc_info:
        service._validate_resumable(run, run_id=run.run_id)

    assert exc_info.value.status_code == 409
