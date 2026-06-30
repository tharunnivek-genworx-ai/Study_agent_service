# src/api/core/services/quiz_services/quiz_service.py
"""
Quiz service: business logic for quizzes, quiz_questions, quiz_attempts,
and quiz_question_responses.

Mentor flow (Option B — quiz lifecycle decoupled from SM version identity):
  GENERATE       → ownership guard → require live SM on node → Quiz Agent graph
  GENERATE HINTS → HintService on existing quiz rows (separate flow)
  LIST/GET       → access guard → return quiz(zes) with questions
  PUBLISH        → ownership guard → require live SM on node → set is_published
  QUESTION CRUD  → ownership guard → require live SM on node
  START ATTEMPT  → trainee guard → validate quiz is published (trainee path
                   enforces SM version match when quiz metadata is present)
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    GenerationRunConflictException,
    QuizAlreadyPublishedException,
    QuizCannotDiscardRetiredException,
    QuizHasNoPublishedStudyMaterialException,
    QuizHintsIncompleteException,
    QuizNotFoundException,
    QuizNotPublishedForUnpublishException,
    QuizQuestionNotFoundException,
)
from src.api.core.services import GenerationRunService
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.repositories import (
    MentorProgressRepository,
    QuizRepository,
    StudyMaterialRepository,
)
from src.api.schemas import (
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.schemas.quiz_schemas import (
    CorrectOption,
    QuizDeleteOut,
    QuizGenerateRequest,
    QuizHistoryItemOut,
    QuizMentorUiStateOut,
    QuizOut,
    QuizPublishRequest,
    QuizQuestionCreateRequest,
    QuizQuestionDeletedOut,
    QuizQuestionOut,
    QuizQuestionRegenerateRequest,
    QuizQuestionReorderRequest,
    QuizQuestionUpdateRequest,
    QuizUnpublishPreviewOut,
    QuizUnpublishRequest,
)
from src.api.schemas.study_material_schemas import RetentionMode
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DRAFT,
)
from src.api.utils.content_lifecycle.transitions import (
    transition_quiz_to_archived,
    transition_quiz_to_hidden,
)
from src.api.utils.content_lifecycle.visibility import is_discarded
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)
from src.api.utils.quiz_utils.hints_status import compute_hints_status
from src.api.utils.quiz_utils.mentor_quiz_history import (
    can_delete_history_quiz,
    history_status_badge,
    is_mentor_history_quiz,
    resolve_history_version_label,
)
from src.api.utils.quiz_utils.mentor_quiz_state import (
    find_other_live_quiz,
    mentor_quiz_draft_exists,
    resolve_mentor_quiz_id,
)
from src.api.utils.quiz_utils.mentor_quiz_ui import compute_mentor_quiz_ui_flags
from src.api.utils.quiz_utils.study_material_link import (
    get_mentor_quiz_study_material_source,
    require_mentor_quiz_study_material_source,
    require_published_study_material_for_node,
    validate_quiz_can_be_published,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _get_node_and_assert_space_access,
    _get_space_and_assert_owner,
)
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)
from src.api.utils.trainee_progress_utils.progress_resets import (
    reset_node_quiz_passed_for_all_trainees,
)

logger = logging.getLogger(__name__)


def _quiz_run_mode(mode: str) -> GenerationRunMode:
    if mode == "regenerate":
        return GenerationRunMode.REGENERATE
    return GenerationRunMode.GENERATE


def _validate_question_options(
    *,
    option_a: str | None,
    option_b: str | None,
    option_c: str | None,
    option_d: str | None,
    correct_option: CorrectOption,
) -> None:
    """Ensure all four options are non-empty and correct_option references one."""
    options = {
        "A": option_a,
        "B": option_b,
        "C": option_c,
        "D": option_d,
    }
    for letter, value in options.items():
        if value is None or not str(value).strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"option_{letter.lower()} is required and must be non-empty.",
            )
    if correct_option not in options or not str(options[correct_option]).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="correct_option must reference a non-empty option.",
        )


class QuizService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _start_quiz_run(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        mentor_id: UUID,
        generation_mode: GenerationRunMode,
        request_params: dict[str, Any],
        quiz_id: UUID | None = None,
    ) -> UUID:
        resource_type, resource_id = GenerationRunService.resource_for_quiz_generation(
            node_id,
            quiz_id=quiz_id,
        )
        run_service = GenerationRunService(self.session)
        run = await run_service.start_run(
            GenerationRunCreate(
                pipeline=GenerationRunPipeline.QUIZ,
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
        error_message = str(exc) if exc is not None else "Quiz generation failed."
        error_type = type(exc).__name__ if exc is not None else "generation_failed"
        next_retry = None
        if graph_result is not None:
            raw_retry = graph_result.get("next_llm_retry_at")
            if isinstance(raw_retry, datetime):
                next_retry = raw_retry
            error_message = str(graph_result.get("error") or error_message)
            if graph_result.get("terminal_llm_failure"):
                error_type = str(graph_result.get("llm_error_type") or error_type)
        await GenerationRunService(self.session).fail_run(
            run_id,
            error_message=error_message,
            error_type=error_type,
            next_llm_retry_at=next_retry,
        )

    async def _build_quiz_out(
        self,
        quiz_id: UUID,
        *,
        run_id: UUID | None = None,
        hints_stale_question_ids: list[UUID] | None = None,
    ) -> QuizOut:
        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None:
            from src.api.core.exceptions import (  # noqa: PLC0415
                QuizGenerationFailedException,
            )

            raise QuizGenerationFailedException()
        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        if hints_stale_question_ids is not None:
            quiz_out.hints_stale_question_ids = hints_stale_question_ids
        if run_id is not None:
            quiz_out.run_id = run_id
            quiz_out.progress_session_id = run_id
        return quiz_out

    async def _assert_no_concurrent_quiz_work(self, quiz_id: UUID) -> None:
        """Reject when a quiz or hint generation run is already in progress."""
        run_service = GenerationRunService(self.session)
        for pipeline in (GenerationRunPipeline.QUIZ, GenerationRunPipeline.HINT):
            _, resource_id = (
                GenerationRunService.resource_for_hint(quiz_id)
                if pipeline == GenerationRunPipeline.HINT
                else GenerationRunService.resource_for_quiz(quiz_id)
            )
            active = await run_service.repo.get_active_run(
                resource_id=resource_id,
                pipeline=pipeline.value,
            )
            if (
                active is not None
                and active.status == GenerationRunStatus.RUNNING.value
            ):
                raise GenerationRunConflictException(str(active.run_id))

    async def _run_quiz_single_regen_graph(
        self,
        *,
        initial_state: dict[str, Any],
        run_id: UUID,
    ) -> dict[str, Any]:
        from src.api.control.quiz_agent.graph.quiz_single_regen_graph.runner import (
            run_quiz_single_regen,
        )
        from src.api.core.exceptions import (  # noqa: PLC0415
            QuizGenerationFailedException,
        )

        try:
            final_state = await run_quiz_single_regen(
                self.session,
                initial_state,
                run_id=run_id,
            )
            if final_state.get("terminal_llm_failure"):
                await self._fail_generation_run(run_id, graph_result=final_state)
                raise QuizGenerationFailedException(
                    "Question rework failed due to a temporary LLM error. "
                    "You can resume this run when retry is available."
                )
            if final_state.get("error"):
                await self._fail_generation_run(run_id, graph_result=final_state)
                raise QuizGenerationFailedException(str(final_state["error"]))
            await self._complete_generation_run(run_id)
            return final_state
        except QuizGenerationFailedException:
            raise
        except Exception as exc:
            graph_result = exc.__dict__.get("graph_result")
            if isinstance(graph_result, dict):
                await self._fail_generation_run(
                    run_id, graph_result=graph_result, exc=exc
                )
            else:
                await self._fail_generation_run(run_id, exc=exc)
            raise

    async def resume_quiz_generation(
        self,
        resume_result: GenerationRunResumeResult,
        *,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Continue a failed quiz run from its last checkpoint."""
        from src.api.control.quiz_agent.graph.quiz_graph.resume_router import (
            hydrate_checkpoint_state,
        )
        from src.api.control.quiz_agent.graph.quiz_graph.runner import (
            run_quiz_from_checkpoint,
        )
        from src.api.core.exceptions import (  # noqa: PLC0415
            QuizGenerationFailedException,
        )

        _assert_mentor(role)
        node_id = resume_result.checkpoint_state.get("node_id")
        if node_id is None:
            node_id = resume_result.request_params.get("node_id")
        if isinstance(node_id, str):
            node_id = UUID(node_id)
        if node_id is None:
            raise QuizGenerationFailedException("Resume checkpoint is missing node_id.")

        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        run_id = resume_result.run_id
        initial_state = hydrate_checkpoint_state(
            resume_result.checkpoint_state,
            last_completed_node=resume_result.last_completed_node,
            request_params=resume_result.request_params,
        )
        initial_state["mentor_id"] = user_id

        try:
            final_state = await run_quiz_from_checkpoint(
                self.session,
                initial_state,
                run_id=run_id,
            )
            created_quiz_id = final_state.get("created_quiz_id")
            if created_quiz_id is None:
                if final_state.get("error"):
                    raise QuizGenerationFailedException(str(final_state["error"]))
                raise QuizGenerationFailedException(
                    "Quiz generation failed. Please try again."
                )
            await self._complete_generation_run(run_id)
            if isinstance(created_quiz_id, str):
                created_quiz_id = UUID(created_quiz_id)
            return await self._build_quiz_out(created_quiz_id, run_id=run_id)
        except Exception as exc:
            graph_result = exc.__dict__.get("graph_result")
            if isinstance(graph_result, dict):
                await self._fail_generation_run(
                    run_id, graph_result=graph_result, exc=exc
                )
            else:
                await self._fail_generation_run(run_id, exc=exc)
            raise

    async def resume_question_rework(
        self,
        resume_result: GenerationRunResumeResult,
        *,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Continue a failed single-question rework run from its last checkpoint."""
        from src.api.control.quiz_agent.graph.quiz_single_regen_graph.resume_router import (
            hydrate_checkpoint_state,
        )
        from src.api.control.quiz_agent.graph.quiz_single_regen_graph.runner import (
            run_quiz_single_regen_from_checkpoint,
        )
        from src.api.core.exceptions import (  # noqa: PLC0415
            QuizGenerationFailedException,
        )

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
            raise QuizGenerationFailedException(
                "Resume checkpoint is missing node_id or quiz_id."
            )

        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        run_id = resume_result.run_id
        initial_state = hydrate_checkpoint_state(
            resume_result.checkpoint_state,
            last_completed_node=resume_result.last_completed_node,
            request_params=resume_result.request_params,
        )
        initial_state["mentor_id"] = user_id

        try:
            final_state = await run_quiz_single_regen_from_checkpoint(
                self.session,
                initial_state,
                run_id=run_id,
            )
            if final_state.get("terminal_llm_failure"):
                await self._fail_generation_run(run_id, graph_result=final_state)
                raise QuizGenerationFailedException(
                    "Question rework failed due to a temporary LLM error. "
                    "You can resume this run when retry is available."
                )
            if final_state.get("error"):
                await self._fail_generation_run(run_id, graph_result=final_state)
                raise QuizGenerationFailedException(str(final_state["error"]))
            await self._complete_generation_run(run_id)
            hints_stale = self._coerce_stale_question_ids(
                final_state.get("hints_stale_question_ids") or []
            )
            return await self._build_quiz_out(
                quiz_id,
                run_id=run_id,
                hints_stale_question_ids=hints_stale,
            )
        except QuizGenerationFailedException:
            raise
        except Exception as exc:
            graph_result = exc.__dict__.get("graph_result")
            if isinstance(graph_result, dict):
                await self._fail_generation_run(
                    run_id, graph_result=graph_result, exc=exc
                )
            else:
                await self._fail_generation_run(run_id, exc=exc)
            raise

    @staticmethod
    def _coerce_stale_question_ids(raw_ids: list[Any]) -> list[UUID]:
        stale: list[UUID] = []
        for value in raw_ids:
            if isinstance(value, UUID):
                stale.append(value)
            elif isinstance(value, str):
                stale.append(UUID(value))
        return stale

    async def _require_quiz_study_material_source(
        self, node_id: UUID
    ) -> StudyMaterialVersion:
        sm_repo = StudyMaterialRepository(self.session)
        return await require_mentor_quiz_study_material_source(sm_repo, node_id=node_id)

    async def _require_published_study_material_for_node(self, node_id: UUID) -> None:
        sm_repo = StudyMaterialRepository(self.session)
        await require_published_study_material_for_node(sm_repo, node_id=node_id)

    # ── generate ───────────────────────────────────────────────────────

    async def generate_quiz(
        self,
        node_id: UUID,
        request: QuizGenerateRequest,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Generate a new quiz draft using the Quiz Agent LangGraph.

        For mode='generate': creates a fresh quiz from the published study material.
        For mode='regenerate': loads existing quiz questions as context and generates
        a new quiz draft, using quiz_id (required) as the source quiz.
        """
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        sm_repo = StudyMaterialRepository(self.session)
        source_sm = await get_mentor_quiz_study_material_source(
            sm_repo, node_id=node_id
        )

        failed_qc_feedback = None
        regenerate_from_retired = False
        if request.mode == "regenerate" and request.quiz_id is not None:
            source_quiz = await repo.get_quiz_by_id(request.quiz_id)
            if source_quiz is None or source_quiz.node_id != node_id:
                raise QuizNotFoundException()
            if source_quiz.qc_failed_permanently and source_quiz.qc_result:
                from src.api.utils.quiz_utils.quality_check_utils.results.feedback import (  # noqa: PLC0415
                    format_qc_feedback,
                )

                failed_qc_feedback = format_qc_feedback(source_quiz.qc_result)
            if source_quiz.lifecycle_status != LIFECYCLE_DRAFT:
                regenerate_from_retired = True

        # M10: one active draft per node — regenerate in-place when a draft exists.
        effective_mode = request.mode
        effective_quiz_id = request.quiz_id
        if regenerate_from_retired:
            effective_mode = "generate"
            effective_quiz_id = None
        elif request.mode == "generate":
            existing_draft = await repo.get_active_quiz_draft_for_node(node_id)
            if existing_draft is not None:
                sm_stale = (
                    existing_draft.study_material_version_id is not None
                    and existing_draft.study_material_version_id != source_sm.version_id
                )
                if sm_stale:
                    # Fresh generation from the new live SM; replace the stale
                    # draft in-place without loading old questions as context.
                    effective_mode = "generate"
                    effective_quiz_id = existing_draft.quiz_id
                else:
                    effective_mode = "regenerate"
                    effective_quiz_id = existing_draft.quiz_id
        from src.api.control.quiz_agent.graph.quiz_graph.runner import (
            run_quiz_generation,
        )
        from src.api.core.exceptions import (
            QuizGenerationFailedException,
        )

        run_id = await self._start_quiz_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            generation_mode=_quiz_run_mode(effective_mode),
            quiz_id=effective_quiz_id,
            request_params={
                "question_count": request.question_count,
                "difficulty": request.difficulty,
                "mode": effective_mode,
                "quiz_id": str(effective_quiz_id) if effective_quiz_id else None,
                "mentor_feedback": request.mentor_feedback,
                "title": request.title,
            },
        )

        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "mode": effective_mode,
            "quiz_id": effective_quiz_id,
            "question_count": request.question_count,
            "difficulty": request.difficulty,
            "mentor_feedback": request.mentor_feedback,
            "space_id": None,
            "study_material_version_id": source_sm.version_id,
            "study_material_content": None,
            "qc_passed": False,
            "qc_feedback": "",
            "qc_attempt": 0,
            "qc_failed_permanently": False,
            "failed_qc_feedback": failed_qc_feedback,
        }

        try:
            final_state = await run_quiz_generation(
                self.session,
                initial_state,
                run_id=run_id,
            )

            if final_state is None:
                raise QuizGenerationFailedException()

            created_quiz_id = final_state.get("created_quiz_id")
            if created_quiz_id is None:
                if final_state.get("error"):
                    await self._fail_generation_run(
                        run_id,
                        graph_result=final_state,
                        exc=QuizGenerationFailedException(str(final_state["error"])),
                    )
                    raise QuizGenerationFailedException(str(final_state["error"]))
                await self._fail_generation_run(
                    run_id,
                    graph_result=final_state,
                    exc=QuizGenerationFailedException(
                        "Quiz generation failed. Please try again."
                    ),
                )
                raise QuizGenerationFailedException(
                    "Quiz generation failed. Please try again."
                )

            if final_state.get("error") and not final_state.get("terminal_llm_failure"):
                await self._fail_generation_run(
                    run_id,
                    graph_result=final_state,
                    exc=QuizGenerationFailedException(str(final_state["error"])),
                )
                raise QuizGenerationFailedException(str(final_state["error"]))

            await self._complete_generation_run(run_id)
            if isinstance(created_quiz_id, str):
                created_quiz_id = UUID(created_quiz_id)
            return await self._build_quiz_out(created_quiz_id, run_id=run_id)
        except QuizGenerationFailedException:
            raise
        except Exception as exc:
            await self._fail_generation_run(run_id, exc=exc)
            raise

    async def regenerate_questions(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizQuestionRegenerateRequest,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Rework one or more active quiz questions in-place via mentor feedback."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published:
            raise QuizAlreadyPublishedException()
        await self._require_quiz_study_material_source(node_id)

        payload_ids = set(request.question_ids)
        matched = await repo.get_active_questions_by_ids(quiz_id, request.question_ids)
        matched_ids = {question.question_id for question in matched}
        if matched_ids != payload_ids:
            raise QuizQuestionNotFoundException()

        await self._assert_no_concurrent_quiz_work(quiz_id)

        mentor_feedback = request.mentor_feedback.strip()
        run_id = await self._start_quiz_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            generation_mode=GenerationRunMode.IMPROVE,
            quiz_id=quiz_id,
            request_params={
                "node_id": str(node_id),
                "quiz_id": str(quiz_id),
                "mentor_id": str(user_id),
                "question_ids": [str(qid) for qid in request.question_ids],
                "mentor_feedback": mentor_feedback,
            },
        )

        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "quiz_id": quiz_id,
            "question_ids": request.question_ids,
            "mentor_feedback": mentor_feedback,
        }

        final_state = await self._run_quiz_single_regen_graph(
            initial_state=initial_state,
            run_id=run_id,
        )
        hints_stale = self._coerce_stale_question_ids(
            final_state.get("hints_stale_question_ids") or []
        )
        return await self._build_quiz_out(
            quiz_id,
            run_id=run_id,
            hints_stale_question_ids=hints_stale,
        )

    async def get_mentor_quiz_ui_state(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        *,
        preferred_quiz_id: UUID | None = None,
        include_quiz: bool = False,
    ) -> QuizMentorUiStateOut:
        """Resolve mentor quiz UI flags and optionally return the full quiz."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        space_is_published = bool(space.is_published)
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = QuizRepository(self.session)
        sm_repo = StudyMaterialRepository(self.session)
        published = await sm_repo.get_published_version(node_id)
        try:
            source_sm = await get_mentor_quiz_study_material_source(
                sm_repo, node_id=node_id
            )
        except QuizHasNoPublishedStudyMaterialException:
            source_sm = None

        quizzes = await repo.get_quizzes_by_node(node_id)
        resolved_id = resolve_mentor_quiz_id(quizzes, preferred_quiz_id)

        quiz_out: QuizOut | None = None
        if include_quiz and resolved_id is not None:
            quiz_out = await self.get_quiz(node_id, resolved_id, user_id, role)

        quiz_row = None
        hints_status: str | None = None
        if resolved_id is not None and quiz_out is None:
            quiz_row = await repo.get_quiz_by_id(resolved_id)
            active_questions = await repo.get_active_questions_by_quiz(resolved_id)
            hints_status = compute_hints_status(active_questions)
        elif quiz_out is not None:
            hints_status = quiz_out.hints_status

        # Resolve the quiz's SM version label for the nudge banner.
        version_labels: dict[UUID, str] = {}
        quiz_sm_version_id: UUID | None = None
        quiz_sm_version_label: str | None = None
        if quiz_out is not None and quiz_out.study_material_version_id:
            try:
                quiz_sm_version_id = UUID(str(quiz_out.study_material_version_id))
            except (ValueError, AttributeError):
                pass
        elif quiz_row is not None and quiz_row.study_material_version_id:
            quiz_sm_version_id = quiz_row.study_material_version_id
        if quiz_sm_version_id is not None:
            quiz_sm_version_label = await resolve_history_version_label(
                sm_repo, quiz_sm_version_id, version_labels
            )

        other_live_quiz = find_other_live_quiz(quizzes, current_quiz_id=resolved_id)
        flags = compute_mentor_quiz_ui_flags(
            published=published,
            source_sm=source_sm,
            quiz_out=quiz_out,
            quiz_row=quiz_row,
            hints_status=hints_status,
            has_other_live_quiz=other_live_quiz is not None,
            live_sm_version_id=published.version_id if published is not None else None,
            quiz_sm_version_label=quiz_sm_version_label,
        )
        if not space_is_published:
            space_block_reason = (
                "Re-publish this space first to make content visible to trainees."
            )
            flags = {
                **flags,
                "can_generate_quiz": False,
                "generate_disabled_tooltip": space_block_reason,
                "can_access_hints": flags["can_access_hints"],
                "can_generate_hints": False,
                "can_regenerate_hints": False,
                "can_publish_quiz": False,
                "publish_disabled_tooltip": space_block_reason,
            }

        quiz_history: list[QuizHistoryItemOut] = []
        for history_quiz in quizzes:
            if not is_mentor_history_quiz(history_quiz, exclude_quiz_id=resolved_id):
                continue
            sm_version_id = history_quiz.study_material_version_id
            version_label = await resolve_history_version_label(
                sm_repo, sm_version_id, version_labels
            )
            quiz_history.append(
                QuizHistoryItemOut(
                    quiz_id=history_quiz.quiz_id,
                    title=history_quiz.title,
                    status_badge=history_status_badge(history_quiz),
                    lifecycle_status=history_quiz.lifecycle_status,
                    study_material_version_id=sm_version_id,
                    version_label=version_label,
                    total_questions=history_quiz.total_questions,
                    difficulty=history_quiz.difficulty,
                    published_at=history_quiz.published_at,
                    can_view=True,
                    can_delete=can_delete_history_quiz(history_quiz),
                )
            )

        return QuizMentorUiStateOut(
            node_id=node_id,
            resolved_quiz_id=resolved_id,
            quiz_draft_exists=mentor_quiz_draft_exists(quizzes),
            quiz_history=quiz_history,
            published_study_material_version_id=flags[
                "published_study_material_version_id"
            ],
            can_generate_quiz=flags["can_generate_quiz"],
            generate_disabled_tooltip=flags["generate_disabled_tooltip"],
            can_access_hints=flags["can_access_hints"],
            hints_locked=flags["hints_locked"],
            hints_locked_tooltip=flags["hints_locked_tooltip"],
            can_generate_hints=flags["can_generate_hints"],
            can_regenerate_hints=flags["can_regenerate_hints"],
            can_publish_quiz=flags["can_publish_quiz"],
            publish_disabled_tooltip=flags["publish_disabled_tooltip"],
            can_edit_questions=flags["can_edit_questions"],
            can_regenerate_quiz=flags["can_regenerate_quiz"],
            show_update_quiz_nudge=flags["show_update_quiz_nudge"],
            quiz_sm_version_label=flags["quiz_sm_version_label"],
            publish_quiz_button_label=flags["publish_quiz_button_label"],
            unpublish_quiz_button_label=flags["unpublish_quiz_button_label"],
            has_other_live_quiz=other_live_quiz is not None,
            other_live_quiz_title=(
                other_live_quiz.title if other_live_quiz is not None else None
            ),
            quiz=quiz_out,
        )

    async def get_quiz(
        self, node_id: UUID, quiz_id: UUID, user_id: UUID, role: str
    ) -> QuizOut:
        """Fetch a single quiz with its full question list."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()

        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        return quiz_out

    # ── publish ────────────────────────────────────────────────────────

    async def publish_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizPublishRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Set is_published=True on the quiz."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        if not space.is_published:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "ESPACE_NOT_PUBLISHED",
                    "message": (
                        "Re-publish this space first to make content visible to trainees. "
                        "Individual content cannot be published while the space is unpublished."
                    ),
                },
            )

        repo = QuizRepository(self.session)
        sm_repo = StudyMaterialRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published:
            raise QuizAlreadyPublishedException()

        published = await sm_repo.get_published_version(node_id)
        validate_quiz_can_be_published(published_version=published)

        missing = await repo.get_active_questions_missing_hints(quiz_id)
        if missing:
            raise QuizHintsIncompleteException()

        # Capture scalars before repo commit — ORM attributes expire after commit.
        space_id = quiz.space_id

        await repo.publish_quiz(quiz, published_by=user_id)

        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)

        # EC-20: reset quiz_passed for all trainees on this node, then recompute
        # space rollups so completion_status reflects the new quiz requirement.
        try:
            await reset_node_quiz_passed_for_all_trainees(
                self.session,
                node_id=node_id,
                space_id=space_id,
                has_published_quiz=True,
            )
        except Exception:
            logger.warning(
                "publish_quiz: EC-20 quiz_passed reset failed for "
                "space_id=%s node_id=%s",
                space_id,
                node_id,
                exc_info=True,
            )

        return quiz_out

    async def preview_unpublish_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ) -> QuizUnpublishPreviewOut:
        """Return pre-unpublish info with engagement counts without writing."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if not quiz.is_published:
            raise QuizNotPublishedForUnpublishException()

        progress_repo = MentorProgressRepository(self.session)
        trainees_attempt_count = await progress_repo.count_trainees_with_quiz_attempts(
            node_id
        )

        sm_repo = StudyMaterialRepository(self.session)
        published_sm = await sm_repo.get_published_version(node_id)
        version_label: str | None = None
        if published_sm is not None:
            version_label = build_version_display_label(
                published_sm.version_number, published_sm.generation_type
            )

        return QuizUnpublishPreviewOut(
            requires_confirmation=trainees_attempt_count > 0,
            quiz_title=quiz.title,
            trainees_attempt_count=trainees_attempt_count,
            version_label=version_label,
        )

    async def unpublish_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizUnpublishRequest,
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Unpublish quiz with a retention choice; SM lifecycle is unchanged."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if not quiz.is_published:
            raise QuizNotPublishedForUnpublishException()

        space_id = quiz.space_id

        if request.retention_mode == RetentionMode.keep_for_review:
            transition_quiz_to_archived(quiz)
        else:
            transition_quiz_to_hidden(quiz)
        await self.session.commit()

        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)

        # EC-20 / EC-23: quiz unpublish reverts completion to reading-only for
        # trainees who already read the material. Recompute so the cached rollup
        # correctly treats those trainees as 100% complete (no quiz required).
        try:
            await recompute_all_trainees_space_progress(self.session, space_id=space_id)
        except Exception:
            logger.warning(
                "unpublish_quiz: space-progress recompute failed for "
                "space_id=%s node_id=%s — progress data may be stale until "
                "next mentor dashboard refresh",
                space_id,
                node_id,
                exc_info=True,
            )

        return quiz_out

    # ── question management ────────────────────────────────────────────

    async def delete_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ) -> QuizDeleteOut:
        """Soft-discard an unpublished quiz draft from the mentor workspace."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if is_discarded(lifecycle_status=quiz.lifecycle_status):
            raise QuizNotFoundException()
        if quiz.lifecycle_status == LIFECYCLE_ACTIVE or quiz.is_published:
            raise QuizAlreadyPublishedException()
        if quiz.lifecycle_status == LIFECYCLE_ARCHIVED:
            raise QuizCannotDiscardRetiredException()

        discarded = await repo.discard_quiz(quiz_id)
        if discarded == 0:
            raise QuizNotFoundException()
        return QuizDeleteOut(quiz_id=quiz_id, node_id=node_id, deleted=True)

    # ── question management ────────────────────────────────────────────

    async def create_question(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizQuestionCreateRequest,
        user_id: UUID,
        role: str,
    ) -> QuizQuestionOut:
        """Manually add a question. source forced to 'mentor_manual'."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        await self._require_quiz_study_material_source(node_id)

        _validate_question_options(
            option_a=request.option_a,
            option_b=request.option_b,
            option_c=request.option_c,
            option_d=request.option_d,
            correct_option=request.correct_option,
        )

        order_index = request.order_index
        if order_index == 0:
            order_index = await repo.get_next_question_order_index(quiz_id)

        question = await repo.create_question(
            quiz_id=quiz_id,
            node_id=node_id,
            question_text=request.question_text,
            option_a=request.option_a,
            option_b=request.option_b,
            option_c=request.option_c,
            option_d=request.option_d,
            correct_option=request.correct_option,
            hint_1=request.hint_1,
            hint_2=request.hint_2,
            hint_3=request.hint_3,
            explanation=request.explanation,
            order_index=order_index,
            source="mentor_manual",
        )

        # Keep total_questions in sync
        await repo.increment_total_questions(quiz_id)

        await self.session.refresh(question)
        return QuizQuestionOut.model_validate(question)

    async def update_question(
        self,
        node_id: UUID,
        quiz_id: UUID,
        question_id: UUID,
        request: QuizQuestionUpdateRequest,
        user_id: UUID,
        role: str,
    ) -> QuizQuestionOut:
        """Partial update for a question."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        await self._require_quiz_study_material_source(node_id)

        question = await repo.get_question_by_id(question_id)
        if question is None or question.quiz_id != quiz_id or not question.is_active:
            raise QuizQuestionNotFoundException()

        merged_a = (
            request.option_a if request.option_a is not None else question.option_a
        )
        merged_b = (
            request.option_b if request.option_b is not None else question.option_b
        )
        merged_c = (
            request.option_c if request.option_c is not None else question.option_c
        )
        merged_d = (
            request.option_d if request.option_d is not None else question.option_d
        )
        merged_correct = (
            request.correct_option
            if request.correct_option is not None
            else question.correct_option
        )
        if any(
            field is not None
            for field in (
                request.option_a,
                request.option_b,
                request.option_c,
                request.option_d,
                request.correct_option,
            )
        ):
            _validate_question_options(
                option_a=merged_a,
                option_b=merged_b,
                option_c=merged_c,
                option_d=merged_d,
                correct_option=merged_correct,
            )

        question = await repo.update_question(question, request)
        return QuizQuestionOut.model_validate(question)

    async def reorder_questions(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizQuestionReorderRequest,
        user_id: UUID,
        role: str,
    ) -> dict[str, object]:
        """Bulk order_index update. Payload must include all active questions."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        await self._require_quiz_study_material_source(node_id)

        all_active = await repo.get_active_questions_by_quiz(quiz_id)
        all_active_ids = {q.question_id for q in all_active}
        payload_ids = set(request.question_ids)

        if all_active_ids != payload_ids:
            # Mirrors NodeReorderIncompleteException guard
            raise QuizQuestionNotFoundException()

        order_map = {qid: idx for idx, qid in enumerate(request.question_ids)}
        await repo.bulk_update_question_order(order_map)

        return {"detail": "Questions reordered successfully."}

    async def delete_question(
        self,
        node_id: UUID,
        quiz_id: UUID,
        question_id: UUID,
        user_id: UUID,
        role: str,
    ) -> QuizQuestionDeletedOut:
        """Soft-delete a question (is_active=False). Decrements total_questions."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        await self._require_quiz_study_material_source(node_id)

        question = await repo.get_question_by_id(question_id)
        if question is None or question.quiz_id != quiz_id or not question.is_active:
            raise QuizQuestionNotFoundException()

        await repo.soft_delete_question(question)
        await repo.decrement_total_questions(quiz_id)

        return QuizQuestionDeletedOut(question_id=question_id)
