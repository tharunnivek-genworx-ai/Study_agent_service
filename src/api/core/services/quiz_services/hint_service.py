# src/api/core/services/quiz_services/hint_service.py
"""
Hint service: business logic for generating hints on existing quiz questions.

Flow (separate from quiz question generation):
  GENERATE HINTS   → validate ownership → validate quiz is unpublished
                   → validate quiz has active questions missing hints
                   → Hint Agent LangGraph → write hint_1/2/3 on rows → return QuizOut
  REGENERATE HINTS → validate ownership → validate quiz is unpublished
                   → validate question_ids are active and belong to quiz
                   → Hint Agent LangGraph (filtered) → overwrite hints → return QuizOut
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.generation_run_exceptions import (
    GenerationRunConflictException,
)
from src.api.core.exceptions.quiz_exceptions.hint_generation_exceptions import (
    HintGenerationFailedException,
    HintQuestionsNotFoundException,
    HintsAlreadyCompleteException,
    HintsCannotGenerateOnPublishedQuizException,
    HintsNothingToDeleteException,
    QuizHasNoQuestionsException,
)
from src.api.core.exceptions.quiz_exceptions.trainee_quiz_exceptions import (
    QuizNotFoundException,
)
from src.api.core.services.generation_run_service import GenerationRunService
from src.api.data.repositories.quiz_repositories.hint_repository import HintRepository
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.schemas.generation_run_schema import (
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.schemas.quiz_schemas.hint_schema import (
    HintGenerateRequest,
    HintRegenerateRequest,
)
from src.api.schemas.quiz_schemas.quiz_schema import QuizOut, QuizQuestionOut
from src.api.utils.quiz_utils.hints_status import compute_hints_status
from src.api.utils.quiz_utils.study_material_link import (
    require_mentor_quiz_study_material_source,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _get_node_and_assert_space_access,
)

logger = logging.getLogger(__name__)


class HintService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_unpublished_quiz(  # type: ignore[no-untyped-def]
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ):
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = HintRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published:
            raise HintsCannotGenerateOnPublishedQuizException()
        sm_repo = StudyMaterialRepository(self.session)
        await require_mentor_quiz_study_material_source(sm_repo, node_id=node_id)
        return repo, quiz

    async def _start_hint_run(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        mentor_id: UUID,
        quiz_id: UUID,
        generation_mode: GenerationRunMode,
        request_params: dict[str, Any],
    ) -> UUID:
        resource_type, resource_id = GenerationRunService.resource_for_hint(quiz_id)
        run_service = GenerationRunService(self.session)
        run = await run_service.start_run(
            GenerationRunCreate(
                pipeline=GenerationRunPipeline.HINT,
                resource_type=resource_type,
                resource_id=resource_id,
                node_id=node_id,
                space_id=space_id,
                mentor_id=mentor_id,
                generation_mode=generation_mode,
                request_params=request_params,
            )
        )
        return run.run_id

    async def _complete_generation_run(self, run_id: UUID) -> None:
        await GenerationRunService(self.session).complete_run(run_id)

    async def _fail_generation_run(
        self,
        run_id: UUID,
        *,
        graph_result: dict[str, Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        error_message = str(exc) if exc is not None else "Hint generation failed."
        error_type = type(exc).__name__ if exc is not None else "generation_failed"
        next_retry = None
        if graph_result is not None:
            raw_retry = graph_result.get("next_llm_retry_at")
            if isinstance(raw_retry, datetime):
                next_retry = raw_retry
            error_message = str(graph_result.get("error") or error_message)
            if graph_result.get("terminal_llm_failure"):
                error_type = "terminal_llm_failure"
        await GenerationRunService(self.session).fail_run(
            run_id,
            error_message=error_message,
            error_type=error_type,
            next_llm_retry_at=next_retry,
        )

    async def _assert_no_running_hint_generation(self, quiz_id: UUID) -> None:
        resource_type, resource_id = GenerationRunService.resource_for_hint(quiz_id)
        del resource_type
        run_service = GenerationRunService(self.session)
        active = await run_service.repo.get_active_run(
            resource_id=resource_id,
            pipeline=GenerationRunPipeline.HINT.value,
        )
        if active is not None and active.status == GenerationRunStatus.RUNNING.value:
            raise GenerationRunConflictException(str(active.run_id))

    async def _build_quiz_out(
        self,
        quiz_id: UUID,
        quiz: Any,
        *,
        run_id: UUID | None = None,
    ) -> QuizOut:
        """Build a QuizOut from the updated quiz after hint generation."""
        quiz_repo = QuizRepository(self.session)
        questions = await quiz_repo.get_questions_by_quiz(quiz_id)
        active_questions = await quiz_repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        if run_id is not None:
            quiz_out.run_id = run_id
            quiz_out.progress_session_id = run_id
        return quiz_out

    async def _run_hint_graph(
        self,
        *,
        initial_state: dict[str, Any],
        run_id: UUID,
    ) -> dict[str, Any]:
        from src.api.control.hint_agent.graph.runner import run_hint_generation

        progress_id = str(run_id)
        try:
            final_state = await run_hint_generation(
                self.session,
                initial_state,
                progress_session_id=progress_id,
                run_id=run_id,
            )
            await self._complete_generation_run(run_id)
            return final_state
        except Exception as exc:
            graph_result = exc.__dict__.get("graph_result")
            if isinstance(graph_result, dict):
                await self._fail_generation_run(
                    run_id, graph_result=graph_result, exc=exc
                )
            else:
                await self._fail_generation_run(run_id, exc=exc)
            raise

    async def resume_hint_generation(
        self,
        resume_result: GenerationRunResumeResult,
        *,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Continue a failed hint run from its last checkpoint."""
        from src.api.control.hint_agent.graph.resume_router import (
            hydrate_checkpoint_state,
        )
        from src.api.control.hint_agent.graph.runner import run_hint_from_checkpoint

        _assert_mentor(role)
        node_id = resume_result.checkpoint_state.get("node_id")
        quiz_id = resume_result.checkpoint_state.get("quiz_id")
        if node_id is None:
            node_id = resume_result.request_params.get("node_id")
        if quiz_id is None:
            quiz_id = resume_result.request_params.get("quiz_id")
        if isinstance(node_id, str):
            node_id = UUID(node_id)
        if isinstance(quiz_id, str):
            quiz_id = UUID(quiz_id)
        if node_id is None or quiz_id is None:
            raise HintGenerationFailedException(
                "Resume checkpoint is missing node_id or quiz_id."
            )

        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        run_id = resume_result.run_id
        progress_id = str(run_id)
        initial_state = hydrate_checkpoint_state(
            resume_result.checkpoint_state,
            last_completed_node=resume_result.last_completed_node,
            request_params=resume_result.request_params,
        )
        initial_state["mentor_id"] = user_id

        try:
            final_state = await run_hint_from_checkpoint(
                self.session,
                initial_state,
                progress_session_id=progress_id,
                run_id=run_id,
            )
            if final_state.get("error"):
                raise HintGenerationFailedException(str(final_state["error"]))
            await self._complete_generation_run(run_id)
            quiz_repo = QuizRepository(self.session)
            updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
            if updated_quiz is None:
                raise HintGenerationFailedException()
            return await self._build_quiz_out(quiz_id, updated_quiz, run_id=run_id)
        except Exception as exc:
            graph_result = exc.__dict__.get("graph_result")
            if isinstance(graph_result, dict):
                await self._fail_generation_run(
                    run_id, graph_result=graph_result, exc=exc
                )
            else:
                await self._fail_generation_run(run_id, exc=exc)
            raise

    async def generate_hints(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: HintGenerateRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Generate hints for all active questions missing hints via the Hint Agent LangGraph."""
        repo, quiz = await self._get_unpublished_quiz(node_id, quiz_id, user_id, role)

        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        if not active_questions:
            raise QuizHasNoQuestionsException()

        questions_needing_hints = await repo.get_active_questions_missing_hints(quiz_id)
        if not questions_needing_hints:
            raise HintsAlreadyCompleteException()

        await self._assert_no_running_hint_generation(quiz_id)

        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        run_id = await self._start_hint_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            quiz_id=quiz_id,
            generation_mode=GenerationRunMode.GENERATE,
            request_params={
                "node_id": str(node_id),
                "quiz_id": str(quiz_id),
                "mentor_id": str(user_id),
            },
        )

        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "quiz_id": quiz_id,
        }

        await self._run_hint_graph(initial_state=initial_state, run_id=run_id)

        quiz_repo = QuizRepository(self.session)
        updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
        if updated_quiz is None:
            raise HintGenerationFailedException()
        return await self._build_quiz_out(quiz_id, updated_quiz, run_id=run_id)

    async def regenerate_hints(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: HintRegenerateRequest,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Selectively regenerate hints for specific questions via the Hint Agent LangGraph."""
        repo, quiz = await self._get_unpublished_quiz(node_id, quiz_id, user_id, role)

        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        if not active_questions:
            raise QuizHasNoQuestionsException()

        payload_ids = set(request.question_ids)
        matched = await repo.get_active_questions_by_ids(quiz_id, request.question_ids)
        matched_ids = {q.question_id for q in matched}

        if matched_ids != payload_ids:
            raise HintQuestionsNotFoundException()

        await self._assert_no_running_hint_generation(quiz_id)

        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        run_id = await self._start_hint_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            quiz_id=quiz_id,
            generation_mode=GenerationRunMode.REGENERATE,
            request_params={
                "node_id": str(node_id),
                "quiz_id": str(quiz_id),
                "mentor_id": str(user_id),
                "questions_filter_ids": [str(qid) for qid in request.question_ids],
                "mentor_feedback": request.mentor_feedback,
            },
        )

        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "quiz_id": quiz_id,
            "questions_filter_ids": request.question_ids,
            "mentor_feedback": request.mentor_feedback,
        }

        await self._run_hint_graph(initial_state=initial_state, run_id=run_id)

        quiz_repo = QuizRepository(self.session)
        updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
        if updated_quiz is None:
            raise HintGenerationFailedException()
        return await self._build_quiz_out(quiz_id, updated_quiz, run_id=run_id)

    async def delete_hints_draft(
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Clear all generated hints on an unpublished quiz without deleting questions."""
        repo, _quiz = await self._get_unpublished_quiz(node_id, quiz_id, user_id, role)

        cleared = await repo.clear_all_hints_for_quiz(quiz_id)
        if cleared == 0:
            raise HintsNothingToDeleteException()

        quiz_repo = QuizRepository(self.session)
        updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
        return await self._build_quiz_out(quiz_id, updated_quiz)
