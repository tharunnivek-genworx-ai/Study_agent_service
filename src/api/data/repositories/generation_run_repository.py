"""Repository for generationruns checkpoint persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.schemas.generation_run_schema import (
    ACTIVE_RUN_STATUSES,
    GenerationRunCreate,
    GenerationRunStatus,
)


class GenerationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def create(self, payload: GenerationRunCreate) -> GenerationRun:
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
        )
        self.db.add(run)
        await self.db.commit()
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
                    GenerationRun.status == GenerationRunStatus.FAILED.value,
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

    async def complete_run(self, run_id: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                status=GenerationRunStatus.COMPLETED.value,
                completed_at=now,
                updated_at=now,
                error_message=None,
                error_type=None,
            )
        )
        await self.db.commit()

    async def mark_running(self, run_id: UUID) -> None:
        await self.db.execute(
            update(GenerationRun)
            .where(GenerationRun.run_id == run_id)
            .values(
                status=GenerationRunStatus.RUNNING.value,
                updated_at=datetime.now(UTC),
                error_message=None,
                error_type=None,
            )
        )
        await self.db.commit()

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
        await self.db.commit()
        return new_count

    async def cancel_run(self, run_id: UUID) -> bool:
        """Mark a running or failed generation run as cancelled."""
        result = await self.db.execute(
            update(GenerationRun)
            .where(
                and_(
                    GenerationRun.run_id == run_id,
                    GenerationRun.status.in_(
                        (
                            GenerationRunStatus.RUNNING.value,
                            GenerationRunStatus.FAILED.value,
                        )
                    ),
                )
            )
            .values(
                status=GenerationRunStatus.CANCELLED.value,
                error_message="Cancelled by mentor.",
                error_type="cancelled",
                updated_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        await self.db.commit()
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
            GenerationRun.status.in_((GenerationRunStatus.FAILED.value,)),
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
        await self.db.commit()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)
