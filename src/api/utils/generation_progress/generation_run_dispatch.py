"""Dispatch durable generation runs to the correct pipeline executor."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.generation_run_service import GenerationRunService
from src.api.core.services.quiz_services.hint_service import HintService
from src.api.core.services.quiz_services.quiz_service import QuizService
from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.repositories import GenerationRunRepository
from src.api.schemas import (
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResumeResult,
    GenerationRunStatus,
)

logger = logging.getLogger(__name__)


async def execute_scheduled_generation_run(
    session: AsyncSession,
    *,
    run_id: UUID,
    mentor_id: UUID,
    role: str,
    is_resume: bool,
) -> None:
    """Run a generation job body on the worker (fresh start or resume)."""
    run = await GenerationRunRepository(session).get_by_id(run_id)
    if run is None:
        return

    if run.status == GenerationRunStatus.COMPLETED.value:
        logger.info(
            "Skipping generation job for already-completed run",
            extra={"run_id": str(run_id)},
        )
        return

    if is_resume:
        if run.status != GenerationRunStatus.RUNNING.value:
            logger.info(
                "Skipping resume job for non-running run",
                extra={"run_id": str(run_id), "status": run.status},
            )
            return
        run_service = GenerationRunService(session)
        resume_result = GenerationRunResumeResult(
            run_id=run.run_id,
            pipeline=run.pipeline,
            generation_mode=run.generation_mode,
            checkpoint_state=run.checkpoint_state or {},
            request_params=run.request_params or {},
            last_completed_node=run.last_completed_node,
            artifact_run_id=run.artifact_run_id,
            execution_token=run.execution_token,
        )
        await run_service.run_resume_pipeline(
            resume_result,
            mentor_id=mentor_id,
            role=role,
        )
        return

    if run.status != GenerationRunStatus.RUNNING.value:
        logger.info(
            "Skipping generation job for non-running run",
            extra={"run_id": str(run_id), "status": run.status},
        )
        return

    pipeline = run.pipeline
    mode = run.generation_mode
    params: dict[str, Any] = run.request_params or {}

    if pipeline == GenerationRunPipeline.STUDY_MATERIAL.value:
        study_material_service = StudyMaterialService(session)
        if mode == GenerationRunMode.GENERATE.value:
            await study_material_service.execute_generate_study_material(
                run_id=run_id,
                user_id=mentor_id,
            )
        elif mode == GenerationRunMode.REGENERATE.value:
            await study_material_service.execute_regenerate_study_material(
                run_id=run_id,
                user_id=mentor_id,
            )
        elif mode == GenerationRunMode.IMPROVE.value:
            await study_material_service.execute_improve_study_material(
                run_id=run_id,
                user_id=mentor_id,
            )
        return

    if pipeline == GenerationRunPipeline.QUIZ.value:
        quiz_service = QuizService(session)
        if params.get("question_ids"):
            await quiz_service.execute_regenerate_questions(
                run_id=run_id,
                user_id=mentor_id,
            )
        else:
            await quiz_service.execute_generate_quiz(
                run_id=run_id,
                user_id=mentor_id,
            )
        return

    if pipeline == GenerationRunPipeline.HINT.value:
        hint_service = HintService(session)
        if mode == GenerationRunMode.REGENERATE.value:
            await hint_service.execute_regenerate_hints(
                run_id=run_id,
                user_id=mentor_id,
            )
        else:
            await hint_service.execute_generate_hints(
                run_id=run_id,
                user_id=mentor_id,
            )
