# src/api/core/services/trainee_services/trainee_service.py
"""
Service layer for Trainee learning/assessment flow.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    AttemptAbandonedException,
    AttemptAlreadySubmittedException,
    AttemptForbiddenException,
    InvalidSkipPayloadException,
    QuestionAlreadyLockedException,
    QuestionBelongsToAnotherAttemptException,
    QuizAttemptNotFoundException,
    QuizNotFoundException,
    QuizNotPublishedException,
)
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialNoPublishedVersionException,
    StudyMaterialPdfGenerationFailedException,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.trainee_repositories.trainee_repository import (
    TraineeRepository,
)
from src.api.schemas.quiz_schemas.quiz_schema import (
    PublishedQuizDiscoveryOut,
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    TraineeQuizOut,
    TraineeQuizQuestionOut,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialProgressOut,
    StudyMaterialProgressUpdateRequest,
    TraineeStudyMaterialOut,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.quiz_utils.study_material_link import (
    validate_study_material_is_currently_published_for_node,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
)
from src.api.utils.study_agent_utils.study_material_pdf import (
    build_study_material_pdf_filename,
    render_study_material_pdf,
)


def _assert_trainee_owns_attempt(attempt_trainee_id: UUID, user_id: UUID) -> None:
    if attempt_trainee_id != user_id:
        raise AttemptForbiddenException()


class TraineeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TraineeRepository(session)

    # ── Quiz attempt management ──────────────────────────────────────

    async def get_published_quiz_state(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> PublishedQuizDiscoveryOut:
        """Find the published quiz for a node and check for active attempts."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        quiz = await self.repo.get_published_quiz_by_node(node_id)
        if quiz is None:
            return PublishedQuizDiscoveryOut(
                quiz_id=None,
                title=None,
                difficulty=None,
                total_questions=None,
                has_in_progress_attempt=False,
                active_attempt_id=None,
            )

        active_attempt = await self.repo.get_active_attempt_by_quiz_and_trainee(
            quiz.quiz_id, user_id
        )

        return PublishedQuizDiscoveryOut(
            quiz_id=quiz.quiz_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            has_in_progress_attempt=active_attempt is not None,
            active_attempt_id=active_attempt.attempt_id if active_attempt else None,
        )

    async def start_attempt(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizAttemptStartRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,
    ) -> TraineeQuizOut:
        """Create a new attempt and return the full question set with blank state."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        quiz = await self.repo.get_published_quiz_by_node(node_id)
        if quiz is None or quiz.quiz_id != quiz_id:
            raise QuizNotFoundException()
        if not quiz.is_published:
            raise QuizNotPublishedException()

        # Validate study material version linked is still current
        published_sm = await self.repo.get_published_study_material(node_id)
        validate_study_material_is_currently_published_for_node(
            node_id=node_id,
            version_id=quiz.study_material_version_id,
            published_version=published_sm,
        )

        attempt = await self.repo.create_attempt(
            quiz_id=quiz_id,
            node_id=node_id,
            space_id=node.space_id,
            trainee_id=user_id,
        )

        questions = await self.repo.get_active_questions_by_quiz(quiz_id)
        responses_map = await self.repo.get_responses_map(attempt.attempt_id)

        trainee_questions = []
        for q in questions:
            resp = responses_map.get(q.question_id)
            hint_level = resp.hint_level_reached if resp is not None else 0
            trainee_questions.append(
                TraineeQuizQuestionOut(
                    question_id=q.question_id,
                    question_text=q.question_text,
                    option_a=q.option_a,
                    option_b=q.option_b,
                    option_c=q.option_c,
                    option_d=q.option_d,
                    is_active=q.is_active,
                    order_index=q.order_index,
                    hint_1=q.hint_1 if hint_level >= 1 else None,
                    hint_2=q.hint_2 if hint_level >= 2 else None,
                    hint_3=q.hint_3 if hint_level >= 3 else None,
                    hint_level_reached=hint_level,
                    was_skipped=resp.was_skipped if resp is not None else False,
                    was_locked=resp.was_locked if resp is not None else False,
                    selected_option=resp.selected_option if resp is not None else None,
                    is_correct=resp.is_correct if resp is not None else None,
                    correct_option=None,
                    explanation=None,
                )
            )

        return TraineeQuizOut(
            quiz_id=quiz_id,
            node_id=node_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            attempt_id=attempt.attempt_id,
            attempt_status=attempt.status,
            started_at=attempt.started_at,
            questions=trainee_questions,
        )

    async def submit_response(
        self,
        attempt_id: UUID,
        request: QuizQuestionResponseRequest,
        user_id: UUID,
        role: str,  # noqa: ARG002
    ) -> QuizQuestionResponseOut:
        """Record or update a trainee's response for a single question."""
        attempt = await self.repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        if attempt.status == "submitted":
            raise AttemptAlreadySubmittedException()
        if attempt.status == "abandoned":
            raise AttemptAbandonedException()

        if request.was_skipped and request.selected_option is not None:
            raise InvalidSkipPayloadException()

        question = await self.repo.get_question_by_id(request.question_id)
        if question is None or question.quiz_id != attempt.quiz_id:
            raise QuestionBelongsToAnotherAttemptException()

        existing = await self.repo.get_response(attempt_id, request.question_id)
        if existing is not None and existing.was_locked:
            raise QuestionAlreadyLockedException()

        is_correct = None
        was_locked = False
        hint_level = existing.hint_level_reached if existing is not None else 0

        if not request.was_skipped and request.selected_option is not None:
            is_correct = request.selected_option == question.correct_option
            if is_correct:
                was_locked = True
            else:
                hint_level = min(hint_level + 1, 3)

        response = await self.repo.upsert_response(
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=request.selected_option,
            is_correct=is_correct,
            hint_level_reached=hint_level,
            was_skipped=request.was_skipped,
            was_locked=was_locked,
        )

        return QuizQuestionResponseOut(
            response_id=response.response_id,
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=response.selected_option,
            is_correct=response.is_correct,
            hint_level_reached=hint_level,
            was_skipped=response.was_skipped,
            was_locked=response.was_locked,
            hint_1=question.hint_1 if hint_level >= 1 else None,
            hint_2=question.hint_2 if hint_level >= 2 else None,
            hint_3=question.hint_3 if hint_level >= 3 else None,
        )

    async def submit_attempt(
        self,
        attempt_id: UUID,
        request: QuizAttemptSubmitRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,  # noqa: ARG002
    ) -> QuizAttemptOut:
        """Compute score and mark attempt as submitted."""
        attempt = await self.repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        if attempt.status == "submitted":
            raise AttemptAlreadySubmittedException()
        if attempt.status == "abandoned":
            raise AttemptAbandonedException()

        responses = await self.repo.get_all_responses_for_attempt(attempt_id)
        total_questions = await self.repo.get_active_question_count(attempt.quiz_id)

        total_correct = sum(1 for r in responses if r.is_correct)
        total_with_hints = sum(
            1 for r in responses if r.is_correct and r.hint_level_reached > 0
        )
        total_skipped = sum(1 for r in responses if r.was_skipped)
        score = total_correct / total_questions if total_questions > 0 else 0.0

        attempt = await self.repo.submit_attempt(
            attempt=attempt,
            score=score,
            total_correct=total_correct,
            total_with_hints=total_with_hints,
            total_skipped=total_skipped,
        )

        # TODO: notify Engagement & Chat Service of quiz completion and trainee progress updates

        return QuizAttemptOut.model_validate(attempt)

    async def get_attempt(
        self,
        attempt_id: UUID,
        user_id: UUID,
        role: str,  # noqa: ARG002
    ) -> TraineeQuizOut:
        """Fetch attempt details. Resumes mid-progress or reviews submitted state."""
        attempt = await self.repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        quiz = await self.repo.get_published_quiz_by_node(attempt.node_id)
        if quiz is None or quiz.quiz_id != attempt.quiz_id:
            # Quiz might have been unpublished, retrieve it directly
            from src.api.data.repositories.quiz_repositories.quiz_repository import (
                QuizRepository,  # noqa: PLC0415
            )

            quiz_rep = QuizRepository(self.session)
            quiz = await quiz_rep.get_quiz_by_id(attempt.quiz_id)
            if quiz is None:
                raise QuizNotFoundException()

        questions = await self.repo.get_all_questions_by_quiz(attempt.quiz_id)
        responses_map = await self.repo.get_responses_map(attempt_id)

        trainee_questions = []
        for q in questions:
            resp = responses_map.get(q.question_id)
            hint_level = resp.hint_level_reached if resp is not None else 0

            # Populate correct answer and explanation only if submitted
            correct_opt = q.correct_option if attempt.status == "submitted" else None
            exp = q.explanation if attempt.status == "submitted" else None

            trainee_questions.append(
                TraineeQuizQuestionOut(
                    question_id=q.question_id,
                    question_text=q.question_text,
                    option_a=q.option_a,
                    option_b=q.option_b,
                    option_c=q.option_c,
                    option_d=q.option_d,
                    is_active=q.is_active,
                    order_index=q.order_index,
                    hint_1=q.hint_1 if hint_level >= 1 else None,
                    hint_2=q.hint_2 if hint_level >= 2 else None,
                    hint_3=q.hint_3 if hint_level >= 3 else None,
                    hint_level_reached=hint_level,
                    was_skipped=resp.was_skipped if resp is not None else False,
                    was_locked=resp.was_locked if resp is not None else False,
                    selected_option=resp.selected_option if resp is not None else None,
                    is_correct=resp.is_correct if resp is not None else None,
                    correct_option=correct_opt,
                    explanation=exp,
                )
            )

        return TraineeQuizOut(
            quiz_id=attempt.quiz_id,
            node_id=attempt.node_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            attempt_id=attempt_id,
            attempt_status=attempt.status,
            started_at=attempt.started_at,
            questions=trainee_questions,
        )

    # ── Study material management ────────────────────────────────────

    async def get_published_study_material(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> TraineeStudyMaterialOut:
        """Returns the is_published=True study material version for a node."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        version = await self.repo.get_published_study_material(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        result = TraineeStudyMaterialOut.model_validate(version)

        if role == "trainee":
            progress_repo = TraineeNodeProgressRepository(self.session)
            await progress_repo.mark_study_material_viewed(
                user_id, node_id, node.space_id
            )
            await self.session.commit()

        return result

    async def download_published_pdf(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> tuple[bytes, str]:
        """Render the published study material as a PDF for trainees."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        version = await self.repo.get_published_study_material(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        try:
            pdf_bytes = render_study_material_pdf(node.title, version.content)
        except ValueError:
            raise StudyMaterialPdfGenerationFailedException() from None

        filename = build_study_material_pdf_filename(node.title)
        return pdf_bytes, filename

    async def update_study_material_progress(
        self,
        node_id: UUID,
        request: StudyMaterialProgressUpdateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialProgressOut:
        """Trainee scroll progress."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        published = await self.repo.get_published_study_material(node_id)
        if published is None:
            raise StudyMaterialNoPublishedVersionException()

        progress_repo = TraineeNodeProgressRepository(self.session)
        row = await progress_repo.update_read_progress(
            user_id, node_id, node.space_id, request.read_percent
        )
        result = StudyMaterialProgressOut.model_validate(row)
        await self.session.commit()
        return result
