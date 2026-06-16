# src/api/core/services/content_service/quiz_service.py
"""
Quiz service: all business logic for quizzes, quiz_questions,
quiz_attempts, and quiz_question_responses.

Flow per TDD §3.2.2 and §3.2.3:
  GENERATE     → validate ownership → validate study material version is published
                 → (Quiz Agent LLM placeholder) → insert quizzes row + quiz_questions rows
                 (questions only — hints are generated separately)
  GENERATE HINTS → separate HintService / Hint Agent flow on existing quiz rows
  LIST/GET     → access guard → return quiz(zes) with questions
  PUBLISH      → ownership guard → set is_published=True
  ADD QUESTION → ownership guard → validate correct_option references non-None option
                 → insert quiz_questions row → increment total_questions
  UPDATE Q     → ownership guard → partial merge → EC-12 notification placeholder
  REORDER Q    → ownership guard → validate complete active set → bulk update
  DELETE Q     → ownership guard → soft-delete → decrement total_questions
  START ATTEMPT → trainee guard → validate quiz is published → insert quiz_attempts row
                  → return full TraineeQuizOut with blank state (EC-9)
  SUBMIT RESP  → trainee guard → validate attempt is in_progress
                 → validate question belongs to quiz → locked guard (EC-7)
                 → skip guard (EC-8) → upsert response → reveal hint if wrong
  SUBMIT ATTEMPT → trainee guard → compute score → update status='submitted'
  GET ATTEMPT  → trainee guard → merge question + response state (EC-7 resume)
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    AttemptForbiddenException,
    QuizAlreadyPublishedException,
    QuizHintsIncompleteException,
    QuizNotFoundException,
    QuizNotPublishedForUnpublishException,
    QuizQuestionNotFoundException,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.schemas.quiz_schemas.quiz_schema import (
    CorrectOption,
    QuizDeleteOut,
    QuizGenerateRequest,
    QuizListOut,
    QuizMentorUiStateOut,
    QuizOut,
    QuizPublishRequest,
    QuizQuestionCreateRequest,
    QuizQuestionDeletedOut,
    QuizQuestionOut,
    QuizQuestionReorderRequest,
    QuizQuestionUpdateRequest,
    QuizSummaryOut,
    QuizUnpublishRequest,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.quiz_utils.hints_status import compute_hints_status
from src.api.utils.quiz_utils.mentor_quiz_state import (
    mentor_quiz_draft_exists,
    resolve_mentor_quiz_id,
)
from src.api.utils.quiz_utils.mentor_quiz_ui import compute_mentor_quiz_ui_flags
from src.api.utils.quiz_utils.study_material_link import (
    validate_quiz_can_be_published,
    validate_quiz_linked_version_is_published,
    validate_study_material_is_currently_published_for_node,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _get_space_and_assert_owner,
)


def _assert_trainee_owns_attempt(attempt_trainee_id: UUID, user_id: UUID) -> None:
    if attempt_trainee_id != user_id:
        raise AttemptForbiddenException()


def _validate_correct_option_exists(
    correct_option: CorrectOption,
    option_c: str | None,
    option_d: str | None,
) -> None:
    """Ensure correct_option references a non-None option."""
    if correct_option == "C" and option_c is None:
        raise QuizQuestionNotFoundException()
    if correct_option == "D" and option_d is None:
        raise QuizQuestionNotFoundException()


class QuizService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _assert_quiz_linked_version_published(self, node_id: UUID, quiz) -> None:  # type: ignore[no-untyped-def]
        sm_repo = StudyMaterialRepository(self.session)
        await validate_quiz_linked_version_is_published(
            sm_repo,
            node_id=node_id,
            study_material_version_id=quiz.study_material_version_id,
        )

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
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        sm_repo = StudyMaterialRepository(self.session)
        published = await sm_repo.get_published_version(node_id)
        version_id = request.study_material_version_id or (
            published.version_id if published is not None else None
        )
        if version_id is None:
            from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (  # noqa: PLC0415
                QuizHasNoPublishedStudyMaterialException,
            )

            raise QuizHasNoPublishedStudyMaterialException()
        validate_study_material_is_currently_published_for_node(
            node_id=node_id,
            version_id=version_id,
            published_version=published,
        )

        if request.mode == "regenerate" and request.quiz_id is not None:
            source_quiz = await repo.get_quiz_by_id(request.quiz_id)
            if source_quiz is None or source_quiz.node_id != node_id:
                raise QuizNotFoundException()
            validate_study_material_is_currently_published_for_node(
                node_id=node_id,
                version_id=source_quiz.study_material_version_id,
                published_version=published,
            )

        from src.api.control.agents.quiz_generation_graph import (
            get_quiz_generation_graph,  # noqa: PLC0415
        )
        from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
            QuizGenerationFailedException,  # noqa: PLC0415
        )

        graph = get_quiz_generation_graph()
        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "mode": request.mode,
            "quiz_id": request.quiz_id,
            "question_count": request.question_count,
            "difficulty": request.difficulty,
            "mentor_feedback": request.mentor_feedback,
            "space_id": None,
            "study_material_version_id": published.version_id,  # type: ignore[union-attr]
            "study_material_content": None,
        }

        final_state = None
        last_error: str | None = None
        for attempt in range(2):
            final_state = await graph.ainvoke(
                initial_state,
                config={"configurable": {"session": self.session}},
            )
            if final_state.get("created_quiz_id"):
                break
            last_error = final_state.get("error")
            if attempt == 0 and last_error:
                continue

        if final_state is None:
            raise QuizGenerationFailedException()

        if final_state.get("error"):
            raise QuizGenerationFailedException(str(final_state["error"]))

        created_quiz_id = final_state.get("created_quiz_id")
        if created_quiz_id is None:
            raise QuizGenerationFailedException(
                last_error or "Quiz generation failed. Please try again."
            )

        quiz = await repo.get_quiz_by_id(created_quiz_id)
        if quiz is None:
            raise QuizGenerationFailedException()

        questions = await repo.get_questions_by_quiz(created_quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(created_quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        return quiz_out

    # ── list / get ─────────────────────────────────────────────────────

    async def list_quizzes(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> QuizListOut:
        """List all quiz generations for a node, ordered by created_at DESC."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = QuizRepository(self.session)
        quizzes = await repo.get_quizzes_by_node(node_id)
        return QuizListOut(
            node_id=node_id,
            quizzes=[QuizSummaryOut.model_validate(q) for q in quizzes],
            total=len(quizzes),
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
        quizzes = await repo.get_quizzes_by_node(node_id)
        resolved_id = resolve_mentor_quiz_id(quizzes, preferred_quiz_id)

        quiz_out: QuizOut | None = None
        if include_quiz and resolved_id is not None:
            quiz_out = await self.get_quiz(node_id, resolved_id, user_id, role)

        quiz_row = None
        hints_status: str | None = None
        linked_version_number: int | None = None
        linked_generation_type: str | None = None
        if resolved_id is not None and quiz_out is None:
            quiz_row = await repo.get_quiz_by_id(resolved_id)
            active_questions = await repo.get_active_questions_by_quiz(resolved_id)
            hints_status = compute_hints_status(active_questions)
        elif quiz_out is not None:
            hints_status = quiz_out.hints_status

        linked_version_id = (
            quiz_out.study_material_version_id
            if quiz_out is not None
            else quiz_row.study_material_version_id
            if quiz_row is not None
            else None
        )
        if linked_version_id is not None:
            linked_version = await sm_repo.get_version_by_id(linked_version_id)
            if linked_version is not None:
                linked_version_number = linked_version.version_number
                linked_generation_type = linked_version.generation_type

        flags = compute_mentor_quiz_ui_flags(
            published=published,
            quiz_out=quiz_out,
            quiz_row=quiz_row,
            hints_status=hints_status,
            linked_version_number=linked_version_number,
            linked_generation_type=linked_generation_type,
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

        return QuizMentorUiStateOut(
            node_id=node_id,
            resolved_quiz_id=resolved_id,
            quiz_draft_exists=mentor_quiz_draft_exists(quizzes),
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
            edit_question_disabled_tooltip=flags["edit_question_disabled_tooltip"],
            regenerate_quiz_disabled_tooltip=flags["regenerate_quiz_disabled_tooltip"],
            is_linked_version_published=flags["is_linked_version_published"],
            is_stale_version=flags["is_stale_version"],
            linked_version_label=flags["linked_version_label"],
            current_published_version_label=flags["current_published_version_label"],
            stale_helper_text=flags["stale_helper_text"],
            generate_new_quiz_cta_label=flags["generate_new_quiz_cta_label"],
            quiz_title_with_version=flags["quiz_title_with_version"],
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
        await validate_quiz_linked_version_is_published(
            sm_repo,
            node_id=node_id,
            study_material_version_id=quiz.study_material_version_id,
        )
        validate_quiz_can_be_published(
            node_id=node_id,
            quiz_study_material_version_id=quiz.study_material_version_id,
            published_version=published,
        )

        missing = await repo.get_active_questions_missing_hints(quiz_id)
        if missing:
            raise QuizHintsIncompleteException()

        quiz = await repo.publish_quiz(quiz, published_by=user_id)
        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        return quiz_out

    async def unpublish_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizUnpublishRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,
    ) -> QuizOut:
        """Clear is_published on the quiz, hiding it from trainees."""
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

        quiz = await repo.unpublish_quiz(quiz)
        questions = await repo.get_questions_by_quiz(quiz_id)
        active_questions = await repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        return quiz_out

    # ── question management ────────────────────────────────────────────

    async def delete_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ) -> QuizDeleteOut:
        """Permanently delete an unpublished quiz draft and all its questions."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published:
            raise QuizAlreadyPublishedException()

        await repo.delete_quiz(quiz)
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
        await self._assert_quiz_linked_version_published(node_id, quiz)

        _validate_correct_option_exists(
            request.correct_option, request.option_c, request.option_d
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
        """Partial update for a question. EC-12 notification is a placeholder."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        await self._assert_quiz_linked_version_published(node_id, quiz)

        question = await repo.get_question_by_id(question_id)
        if question is None or question.quiz_id != quiz_id or not question.is_active:
            raise QuizQuestionNotFoundException()

        # Validate correct_option references a real option after merge
        merged_c = (
            request.option_c if request.option_c is not None else question.option_c
        )
        merged_d = (
            request.option_d if request.option_d is not None else question.option_d
        )
        if request.correct_option is not None:
            _validate_correct_option_exists(request.correct_option, merged_c, merged_d)

        # EC-12: if correct_option changed on a published quiz, emit notification (stub)
        if (
            quiz.is_published
            and request.correct_option is not None
            and request.correct_option != question.correct_option
        ):
            # TODO: emit quiz_questions_edited node_event_notification
            pass

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
        await self._assert_quiz_linked_version_published(node_id, quiz)

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
        await self._assert_quiz_linked_version_published(node_id, quiz)

        question = await repo.get_question_by_id(question_id)
        if question is None or question.quiz_id != quiz_id or not question.is_active:
            raise QuizQuestionNotFoundException()

        await repo.soft_delete_question(question)
        await repo.decrement_total_questions(quiz_id)

        return QuizQuestionDeletedOut(question_id=question_id)
