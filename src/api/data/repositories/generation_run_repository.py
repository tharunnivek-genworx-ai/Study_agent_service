"""Repository for generationruns checkpoint persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.schemas import (
    ACTIVE_RUN_STATUSES,
    GenerationRunCreate,
    GenerationRunStatus,
)


class GenerationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def create(
        self,
        payload: GenerationRunCreate,
        *,
        execution_token: UUID | None = None,
        request_fingerprint: str | None = None,
    ) -> GenerationRun:
        run = GenerationRun(
            run_id=payload.run_id or uuid4(),
            pipeline=payload.pipeline.value,
            resource_type=payload.resource_type.value,
            resource_id=payload.resource_id,
            node_id=payload.node_id,
            space_id=payload.space_id,
            mentor_id=payload.mentor_id,
            status=GenerationRunStatus.RUNNING.value,
            generation_mode=payload.generation_mode.value,
            request_params=payload.request_params,
            artifact_run_id=payload.artifact_run_id,
            progress_step_index=0,
            attempt_count=0,
            execution_token=execution_token,
            request_fingerprint=request_fingerprint,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_by_id(self, run_id: UUID) -> GenerationRun | None:
        result = await self.db.execute(
            select(GenerationRun).where(GenerationRun.run_id == run_id)
        )
        return cast(GenerationRun | None, result.scalars().first())

    async def get_active_run(
        self,
        *,
        resource_id: UUID,
        pipeline: str,
    ) -> GenerationRun | None:
        result = await self.db.execute(
            select(GenerationRun)
            .where(
                and_(
                    GenerationRun.resource_id == resource_id,
                    GenerationRun.pipeline == pipeline,
                    GenerationRun.status.in_(tuple(ACTIVE_RUN_STATUSES)),
                )
            )
            .order_by(GenerationRun.created_at.desc())
            .limit(1)
        )
        return cast(GenerationRun | None, result.scalars().first())

    async def get_resumable_run(
        self,
        *,
        resource_id: UUID,
        pipeline: str,
    ) -> GenerationRun | None:
        result = await self.db.execute(
            select(GenerationRun)
            .where(
                and_(
                    GenerationRun.resource_id == resource_id,
                    GenerationRun.pipeline == pipeline,
                    GenerationRun.status.in_(
                        (
                            GenerationRunStatus.PAUSED.value,
                            GenerationRunStatus.FAILED.value,
                        )
                    ),
                )
            )
            .order_by(GenerationRun.updated_at.desc())
            .limit(1)
        )
        return cast(GenerationRun | None, result.scalars().first())

    async def checkpoint_after_node(
        self,
        run_id: UUID,
        *,
        node_name: str,
        checkpoint_state: dict[str, Any],
        progress_step_index: int | None = None,
        artifact_run_id: str | None = None,
    ) -> GenerationRun | None:
        """Persist checkpoint state; commits for mid-graph durability."""
        values: dict[str, Any] = {
            "last_completed_node": node_name,
            "checkpoint_state": checkpoint_state,
            "updated_at": datetime.now(UTC),
        }
        if progress_step_index is not None:
            values["progress_step_index"] = progress_step_index
        if artifact_run_id is not None:
            values["artifact_run_id"] = artifact_run_id

        await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                )
            )
            .values(**values)
        )
        await self.db.commit()
        return await self.get_by_id(run_id)

    async def update_progress(
        self,
        run_id: UUID,
        *,
        progress_step_index: int,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "progress_step_index": progress_step_index,
            "updated_at": datetime.now(UTC),
        }
        if error_message is not None:
            values["error_message"] = error_message
        await self.db.execute(
            update(GenerationRun).where(GenerationRun.run_id == run_id).values(**values)
        )
        await self.db.flush()

    async def fail_run(
        self,
        run_id: UUID,
        *,
        error_message: str,
        error_type: str | None = None,
        next_llm_retry_at: datetime | None = None,
    ) -> None:
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                status=GenerationRunStatus.FAILED.value,
                error_message=error_message,
                error_type=error_type,
                next_llm_retry_at=next_llm_retry_at,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

    async def complete_run(self, run_id: UUID) -> bool:
        """Mark a run completed only while it is still running."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                )
            )
            .values(
                status=GenerationRunStatus.COMPLETED.value,
                completed_at=now,
                updated_at=now,
                error_message=None,
                error_type=None,
            )
        )
        await self.db.commit()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    async def mark_running(
        self,
        run_id: UUID,
        *,
        execution_token: UUID | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": GenerationRunStatus.RUNNING.value,
            "updated_at": datetime.now(UTC),
            "error_message": None,
            "error_type": None,
            "paused_at": None,
            "pause_reason": None,
        }
        if execution_token is not None:
            values["execution_token"] = execution_token
        await self.db.execute(
            update(GenerationRun).where(GenerationRun.run_id == run_id).values(**values)
        )
        await self.db.flush()

    async def assign_execution_token(self, run_id: UUID, token: UUID) -> None:
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                execution_token=token,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()

    async def pause_run(self, run_id: UUID, *, reason: str = "user") -> bool:
        """Mark a running generation run as paused."""
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                )
            )
            .values(
                status=GenerationRunStatus.PAUSED.value,
                paused_at=datetime.now(UTC),
                pause_reason=reason,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    async def abandon_run(self, run_id: UUID, *, reason: str = "user") -> bool:
        """Mark a generation run as abandoned (running, paused, or failed only)."""
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status.in_(
                        (
                            GenerationRunStatus.RUNNING.value,
                            GenerationRunStatus.PAUSED.value,
                            GenerationRunStatus.FAILED.value,
                        )
                    ),
                )
            )
            .values(
                status=GenerationRunStatus.ABANDONED.value,
                abandoned_at=datetime.now(UTC),
                abandon_reason=reason,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    async def find_stale_running_runs(
        self,
        threshold: datetime,
    ) -> list[GenerationRun]:
        result = await self.db.execute(
            select(GenerationRun).where(
                and_(
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                    GenerationRun.updated_at < threshold,
                )
            )
        )
        return list(result.scalars().all())

    async def mark_stale_failed(self, run_id: UUID) -> bool:
        """Mark a stale running run as failed with resumable stale_worker error."""
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                )
            )
            .values(
                status=GenerationRunStatus.FAILED.value,
                error_type="stale_worker",
                error_message=(
                    "Generation stopped responding. "
                    "You can resume from the last completed step."
                ),
                next_llm_retry_at=None,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    async def store_llamaparse_job_ids(
        self,
        run_id: UUID,
        *,
        extract_id: str | None = None,
        parse_id: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if extract_id is not None:
            values["llamaparse_extract_job_id"] = extract_id
        if parse_id is not None:
            values["llamaparse_parse_job_id"] = parse_id
        if len(values) == 1:
            return
        await self.db.execute(
            update(GenerationRun).where(GenerationRun.run_id == run_id).values(**values)
        )
        await self.db.flush()

    async def increment_attempt_count(self, run_id: UUID) -> int:
        run = await self.get_by_id(run_id)
        if run is None:
            return 0
        new_count = int(run.attempt_count or 0) + 1
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                attempt_count=new_count,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        return new_count

    async def cancel_run(self, run_id: UUID) -> bool:
        """Deprecated: mark run as abandoned for backward compatibility."""
        return await self.abandon_run(run_id, reason="user")

    async def update_request_params(
        self,
        run_id: UUID,
        request_params: dict[str, Any],
    ) -> None:
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                request_params=request_params,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

    async def supersede_other_active_runs(
        self,
        *,
        resource_id: UUID,
        pipeline: str,
        except_run_id: UUID,
    ) -> int:
        """Mark other active rows superseded after a successful inline run."""
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.resource_id == resource_id,
                    GenerationRun.pipeline == pipeline,
                    GenerationRun.run_id != except_run_id,
                    GenerationRun.status.in_(
                        (
                            GenerationRunStatus.RUNNING.value,
                            GenerationRunStatus.PAUSED.value,
                            GenerationRunStatus.FAILED.value,
                        )
                    ),
                )
            )
            .values(
                status=GenerationRunStatus.SUPERSEDED.value,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    async def supersede_stale_runs(
        self,
        *,
        resource_id: UUID,
        pipeline: str,
        except_run_id: UUID | None = None,
    ) -> int:
        conditions = [
            GenerationRun.resource_id == resource_id,
            GenerationRun.pipeline == pipeline,
            GenerationRun.status.in_(
                (
                    GenerationRunStatus.PAUSED.value,
                    GenerationRunStatus.FAILED.value,
                )
            ),
        ]
        if except_run_id is not None:
            conditions.append(GenerationRun.run_id != except_run_id)

        result = await self.db.execute(
            update(GenerationRun)
            .where(and_(*conditions))
            .values(
                status=GenerationRunStatus.SUPERSEDED.value,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0) > 0

    @staticmethod
    def stale_threshold(threshold_minutes: int) -> datetime:
        return datetime.now(UTC) - timedelta(minutes=threshold_minutes)
