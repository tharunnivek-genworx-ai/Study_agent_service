"""Unit tests for Procrastinate batch tasks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.core.exceptions import GenerationRunConflictException
from src.api.schemas.common import GenerationRunStatus


def _make_batch(*, batch_id=None, status: str = "pending", mentor_id=None):
    return SimpleNamespace(
        batch_id=batch_id or uuid4(),
        mentor_id=mentor_id or uuid4(),
        status=status,
        policy={"mode": "skip_existing"},
    )


def _make_step(*, step_id=None, node_id=None):
    return SimpleNamespace(
        step_id=step_id or uuid4(),
        node_id=node_id or uuid4(),
        status="running",
        generation_run_id=None,
        started_at=None,
        error_message=None,
    )


def _session_context(session: MagicMock) -> MagicMock:
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_process_batch_returns_early_for_terminal_batch() -> None:
    from src.api.batch import tasks

    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, status="completed")
    session = _session_context(MagicMock())
    session.rollback = AsyncMock()

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch("src.api.batch.tasks.BatchOrchestrationService") as orchestrator_cls,
        patch(
            "src.api.batch.tasks.release_all_generation_locks",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.batch.tasks.dispatch_batch_job",
            new_callable=AsyncMock,
        ) as dispatch,
    ):
        orchestrator = orchestrator_cls.return_value
        orchestrator._get_batch = AsyncMock(return_value=batch)
        await tasks.process_batch(str(batch_id))

    orchestrator.claim_next_step.assert_not_called()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_process_batch_happy_path_chains_next_step() -> None:
    from src.api.batch import tasks

    batch_id = uuid4()
    run_id = uuid4()
    mentor_id = uuid4()
    batch = _make_batch(batch_id=batch_id, mentor_id=mentor_id)
    step = _make_step()

    claim_session = _session_context(MagicMock())
    claim_session.commit = AsyncMock()
    claim_session.rollback = AsyncMock()

    finalize_session = _session_context(MagicMock())
    finalize_session.commit = AsyncMock()
    finalize_session.rollback = AsyncMock()
    finalize_session.get = AsyncMock(
        return_value=SimpleNamespace(
            run_id=run_id,
            status=GenerationRunStatus.COMPLETED.value,
            error_message=None,
        )
    )

    chain_session = _session_context(MagicMock())
    chain_session.get = AsyncMock(return_value=batch)

    study_material_service = MagicMock()
    study_material_service.start_generate_study_material = AsyncMock(
        return_value=run_id
    )

    with (
        patch(
            "src.api.batch.tasks.SessionLocal",
            side_effect=[claim_session, finalize_session, chain_session],
        ),
        patch("src.api.batch.tasks.BatchOrchestrationService") as orchestrator_cls,
        patch(
            "src.api.batch.tasks.StudyMaterialService",
            return_value=study_material_service,
        ),
        patch(
            "src.api.batch.tasks._execute_generation_run",
            new_callable=AsyncMock,
        ) as execute_run,
        patch(
            "src.api.batch.tasks.release_all_generation_locks",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.batch.tasks.dispatch_batch_job",
            new_callable=AsyncMock,
        ) as dispatch,
        patch(
            "src.api.batch.tasks._batch_has_pending_steps",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        orchestrator = orchestrator_cls.return_value
        orchestrator._get_batch = AsyncMock(return_value=batch)
        orchestrator.claim_next_step = AsyncMock(return_value=step)
        orchestrator.attach_generation_run = AsyncMock()
        orchestrator.finalize_step = AsyncMock()

        await tasks.process_batch(str(batch_id))

    execute_run.assert_awaited_once_with(run_id=run_id, mentor_id=mentor_id)
    orchestrator.attach_generation_run.assert_awaited_once_with(step.step_id, run_id)
    dispatch.assert_awaited_once_with(batch_id)


@pytest.mark.asyncio
async def test_process_batch_conflict_resets_step_and_reraises() -> None:
    from src.api.batch import tasks

    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id)
    step = _make_step()
    session = _session_context(MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()

    study_material_service = MagicMock()
    study_material_service.start_generate_study_material = AsyncMock(
        side_effect=GenerationRunConflictException("Node busy")
    )

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch("src.api.batch.tasks.BatchOrchestrationService") as orchestrator_cls,
        patch(
            "src.api.batch.tasks.StudyMaterialService",
            return_value=study_material_service,
        ),
        patch(
            "src.api.batch.tasks.release_all_generation_locks",
            new_callable=AsyncMock,
        ),
    ):
        orchestrator = orchestrator_cls.return_value
        orchestrator._get_batch = AsyncMock(return_value=batch)
        orchestrator.claim_next_step = AsyncMock(return_value=step)

        with pytest.raises(GenerationRunConflictException):
            await tasks.process_batch(str(batch_id))

    assert step.status == "pending"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_chain_next_step_skips_terminal_batch() -> None:
    from src.api.batch import tasks

    batch_id = uuid4()
    session = _session_context(MagicMock())
    session.get = AsyncMock(
        return_value=_make_batch(batch_id=batch_id, status="completed")
    )

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch(
            "src.api.batch.tasks.dispatch_batch_job",
            new_callable=AsyncMock,
        ) as dispatch,
    ):
        await tasks._maybe_chain_next_step(batch_id)

    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_execute_generation_run_job_reconciles_on_success() -> None:
    from src.api.batch import tasks

    run_id = uuid4()
    with (
        patch(
            "src.api.batch.tasks.run_generation_job",
            new_callable=AsyncMock,
        ) as run_job,
        patch(
            "src.api.batch.tasks._fail_run_if_left_running",
            new_callable=AsyncMock,
        ) as reconcile,
    ):
        await tasks.execute_generation_run_job(str(run_id), str(uuid4()))

    run_job.assert_awaited_once()
    reconcile.assert_awaited_once_with(
        run_id,
        expected_execution_token=None,
    )


@pytest.mark.asyncio
async def test_execute_generation_run_job_reconciles_when_job_raises() -> None:
    from src.api.batch import tasks

    run_id = uuid4()
    with (
        patch(
            "src.api.batch.tasks.run_generation_job",
            new_callable=AsyncMock,
            side_effect=RuntimeError("worker died mid-finalize"),
        ),
        patch(
            "src.api.batch.tasks._fail_run_if_left_running",
            new_callable=AsyncMock,
        ) as reconcile,
    ):
        with pytest.raises(RuntimeError):
            await tasks.execute_generation_run_job(str(run_id), str(uuid4()))

    reconcile.assert_awaited_once_with(
        run_id,
        expected_execution_token=None,
    )


@pytest.mark.asyncio
async def test_fail_run_if_left_running_marks_failed_and_commits() -> None:
    from src.api.batch import tasks

    run_id = uuid4()
    execution_token = uuid4()
    session = _session_context(MagicMock())
    session.commit = AsyncMock()
    repo = MagicMock()
    repo.mark_stale_failed = AsyncMock(return_value=True)

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch(
            "src.api.data.repositories.GenerationRunRepository",
            return_value=repo,
        ),
    ):
        await tasks._fail_run_if_left_running(
            run_id,
            expected_execution_token=execution_token,
        )

    repo.mark_stale_failed.assert_awaited_once_with(
        run_id,
        expected_execution_token=execution_token,
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_run_if_left_running_swallows_errors() -> None:
    from src.api.batch import tasks

    run_id = uuid4()
    session = _session_context(MagicMock())
    session.commit = AsyncMock(side_effect=RuntimeError("db down"))
    repo = MagicMock()
    repo.mark_stale_failed = AsyncMock(return_value=True)

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch(
            "src.api.data.repositories.GenerationRunRepository",
            return_value=repo,
        ),
    ):
        # Reconciliation must never raise out of the task's finally block.
        await tasks._fail_run_if_left_running(
            run_id,
            expected_execution_token=uuid4(),
        )


@pytest.mark.asyncio
async def test_reconcile_running_step_finalizes_terminal_run() -> None:
    from src.api.batch import tasks

    batch_id = uuid4()
    mentor_id = uuid4()
    run_id = uuid4()
    step = _make_step()
    step.generation_run_id = run_id

    session = MagicMock()
    session.get = AsyncMock(
        return_value=SimpleNamespace(
            run_id=run_id,
            status=GenerationRunStatus.COMPLETED.value,
            error_message=None,
        )
    )

    orchestrator = MagicMock()
    orchestrator.finalize_step = AsyncMock()

    with (
        patch(
            "src.api.batch.tasks._get_running_step",
            new_callable=AsyncMock,
            return_value=step,
        ),
        patch(
            "src.api.batch.tasks.BatchOrchestrationService",
            return_value=orchestrator,
        ),
    ):
        reconciled = await tasks._reconcile_running_step(
            session,
            batch_id=batch_id,
            mentor_id=mentor_id,
        )

    assert reconciled is True
    orchestrator.finalize_step.assert_awaited_once()
