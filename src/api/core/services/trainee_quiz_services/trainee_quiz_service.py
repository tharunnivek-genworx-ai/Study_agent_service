# src/api/core/services/trainee_quiz_services/trainee_quiz_service.py
"""
Service layer for trainee quiz attempt flow.

Quiz discovery, attempt lifecycle, and question response handling live here.
Study material delivery is in ``TraineeStudyService``; panel aggregation is
in ``TraineeNodePanelService``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    AttemptAbandonedException,
    AttemptAlreadyInProgressException,
    AttemptAlreadySubmittedException,
    AttemptForbiddenException,
    InvalidSkipPayloadException,
    QuestionAlreadyLockedException,
    QuestionBelongsToAnotherAttemptException,
    QuizAttemptNotFoundException,
    QuizNotFoundException,
    QuizNotPublishedException,
)
from src.api.core.services import (
    TraineeProgressService,
)
from src.api.data.models.postgres.e_learning_content.quiz_attempts import QuizAttempt
from src.api.data.models.postgres.e_learning_content.quiz_question_responses import (
    QuizQuestionResponse,
)
from src.api.data.models.postgres.e_learning_content.quiz_questions import QuizQuestion
from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.repositories import (
    TraineeQuizRepository,
    TraineeStudyRepository,
)
from src.api.schemas.quiz_schemas import (
    ArchivedQuizReviewOut,
    PublishedQuizDiscoveryOut,
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    TraineeArchivedQuizGroupOut,
    TraineeArchivedQuizItemOut,
    TraineeArchivedQuizListOut,
    TraineeQuizAttemptListOut,
    TraineeQuizAttemptSummaryOut,
    TraineeQuizOut,
    TraineeQuizQuestionOut,
)
from src.api.utils.content_lifecycle import (
    list_trainee_archive_quizzes,
    list_trainee_archive_sm,
)
from src.api.utils.content_lifecycle.archive_gates import (
    assert_archive_list_gate,
    assert_archived_quiz_access,
    assert_trainee_archive_context,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_HIDDEN,
)
from src.api.utils.quiz_utils.study_material_link import (
    validate_study_material_is_currently_published_for_node,
)
from src.api.utils.quiz_utils.trainee_attempt_navigation import (
    can_answer_question,
    can_skip_question,
    compute_nav_status,
    compute_resume_question_id,
    count_skipped_at_submit,
    is_question_skipped_at_submit,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
    _get_node_and_assert_space_access,
)
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)


def _assert_trainee_owns_attempt(attempt_trainee_id: UUID, user_id: UUID) -> None:
    if attempt_trainee_id != user_id:
        raise AttemptForbiddenException()


def _score_percent(score: float | None) -> int | None:
    if score is None:
        return None
    return round(score * 100)


def _format_attempt_label(
    *,
    status: str,
    started_at: datetime,
    submitted_at: datetime | None,
    attempt_number: int,
) -> str:
    stamp = submitted_at or started_at
    formatted = stamp.strftime("%b %d, %Y %I:%M %p")
    if status == "in_progress":
        return f"Attempt {attempt_number} · In progress · Started {formatted}"
    return f"Attempt {attempt_number} · {formatted}"


def _pick_archive_review_attempt(
    attempts: list[QuizAttempt],
) -> QuizAttempt | None:
    """Prefer submitted, then frozen/abandoned partial, then any attempt."""
    if not attempts:
        return None
    for attempt in attempts:
        if attempt.status == "submitted":
            return attempt
    for attempt in attempts:
        if attempt.status == "abandoned":
            return attempt
    for attempt in attempts:
        if attempt.status == "in_progress":
            return attempt
    return attempts[0]


class TraineeQuizService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TraineeQuizRepository(session)
        self.study_repo = TraineeStudyRepository(session)

    def _build_question_out(
        self,
        question: QuizQuestion,
        response: QuizQuestionResponse | None,
        *,
        attempt_submitted: bool,
    ) -> TraineeQuizQuestionOut:
        hint_level = response.hint_level_reached if response is not None else 0
        was_locked = response.was_locked if response is not None else False
        skipped_at_submit = is_question_skipped_at_submit(question, response)
        was_skipped = skipped_at_submit if attempt_submitted else False

        return TraineeQuizQuestionOut(
            question_id=question.question_id,
            question_text=question.question_text,
            option_a=question.option_a,
            option_b=question.option_b,
            option_c=question.option_c,
            option_d=question.option_d,
            is_active=question.is_active,
            order_index=question.order_index,
            hint_1=question.hint_1 if hint_level >= 1 else None,
            hint_2=question.hint_2 if hint_level >= 2 else None,
            hint_3=question.hint_3 if hint_level >= 3 else None,
            hint_level_reached=hint_level,
            was_skipped=was_skipped,
            was_locked=was_locked,
            selected_option=response.selected_option if response is not None else None,
            is_correct=response.is_correct if response is not None else None,
            correct_option=question.correct_option if attempt_submitted else None,
            explanation=question.explanation if attempt_submitted else None,
            nav_status=compute_nav_status(
                response,
                attempt_submitted=attempt_submitted,
                skipped_at_submit=skipped_at_submit,
            ),
            can_answer=can_answer_question(
                is_active=question.is_active,
                attempt_submitted=attempt_submitted,
                was_locked=was_locked,
            ),
            can_skip=can_skip_question(
                is_active=question.is_active,
                attempt_submitted=attempt_submitted,
                was_locked=was_locked,
            ),
        )

    def _build_trainee_quiz_out(
        self,
        *,
        quiz: Quiz,
        attempt: QuizAttempt,
        questions: list[QuizQuestion],
        responses_map: dict[UUID, QuizQuestionResponse],
    ) -> TraineeQuizOut:
        attempt_submitted = attempt.status == "submitted"
        trainee_questions = [
            self._build_question_out(
                q, responses_map.get(q.question_id), attempt_submitted=attempt_submitted
            )
            for q in questions
        ]
        resume_question_id = None
        if attempt.status == "in_progress":
            resume_question_id = compute_resume_question_id(questions, responses_map)

        return TraineeQuizOut(
            quiz_id=quiz.quiz_id,
            node_id=quiz.node_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            attempt_id=attempt.attempt_id,
            attempt_status=attempt.status,
            started_at=attempt.started_at,
            resume_question_id=resume_question_id,
            score_percent=_score_percent(attempt.score),
            total_correct=attempt.total_correct if attempt_submitted else None,
            total_skipped=attempt.total_skipped if attempt_submitted else None,
            questions=trainee_questions,
        )

    async def _get_quiz_for_attempt(self, attempt: QuizAttempt) -> Quiz:
        quiz = await self.repo.get_quiz_by_id(attempt.quiz_id)
        if quiz is None:
            raise QuizNotFoundException()
        if quiz.is_published and quiz.lifecycle_status == LIFECYCLE_ACTIVE:
            return quiz
        if quiz.lifecycle_status in (LIFECYCLE_HIDDEN, LIFECYCLE_ARCHIVED):
            attempts = await self.repo.list_attempts_by_quiz_and_trainee(
                quiz.quiz_id, attempt.trainee_id
            )
            if attempts:
                return quiz
        raise QuizNotFoundException()

    async def _resolve_quiz_for_trainee_access(
        self,
        *,
        node_id: UUID,
        quiz_id: UUID,
        trainee_id: UUID,
    ) -> Quiz:
        """Allow published quizzes or hidden quizzes the trainee already attempted."""
        quiz = await self.repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published and quiz.lifecycle_status == LIFECYCLE_ACTIVE:
            return quiz
        if quiz.lifecycle_status in (LIFECYCLE_HIDDEN, LIFECYCLE_ARCHIVED):
            attempts = await self.repo.list_attempts_by_quiz_and_trainee(
                quiz_id, trainee_id
            )
            if attempts:
                return quiz
        raise QuizNotFoundException()

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
            hidden = await self.repo.get_hidden_quiz_with_trainee_attempts(
                node_id, user_id
            )
            if hidden is None:
                return PublishedQuizDiscoveryOut()
            active_attempt = await self.repo.get_active_attempt_by_quiz_and_trainee(
                hidden.quiz_id, user_id
            )
            submitted_count = (
                await self.repo.count_submitted_attempts_by_quiz_and_trainee(
                    hidden.quiz_id, user_id
                )
            )
            return PublishedQuizDiscoveryOut(
                quiz_id=hidden.quiz_id,
                title=hidden.title,
                difficulty=hidden.difficulty,
                total_questions=hidden.total_questions,
                has_in_progress_attempt=active_attempt is not None,
                active_attempt_id=(
                    active_attempt.attempt_id if active_attempt else None
                ),
                submitted_attempt_count=submitted_count,
                can_start_new_attempt=False,
                can_view_previous_attempts=submitted_count > 0
                or active_attempt is not None,
                is_review_only=True,
                review_notice=(
                    "This quiz was unpublished by your mentor. "
                    "You can review your past attempts but cannot start a new one."
                ),
            )

        active_attempt = await self.repo.get_active_attempt_by_quiz_and_trainee(
            quiz.quiz_id, user_id
        )
        submitted_count = await self.repo.count_submitted_attempts_by_quiz_and_trainee(
            quiz.quiz_id, user_id
        )

        return PublishedQuizDiscoveryOut(
            quiz_id=quiz.quiz_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            has_in_progress_attempt=active_attempt is not None,
            active_attempt_id=active_attempt.attempt_id if active_attempt else None,
            submitted_attempt_count=submitted_count,
            can_start_new_attempt=active_attempt is None,
            can_view_previous_attempts=submitted_count > 0
            or active_attempt is not None,
        )

    async def list_attempts(
        self, node_id: UUID, quiz_id: UUID, user_id: UUID, role: str
    ) -> TraineeQuizAttemptListOut:
        """List all attempts for the trainee on this quiz, newest first."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        quiz = await self._resolve_quiz_for_trainee_access(
            node_id=node_id, quiz_id=quiz_id, trainee_id=user_id
        )

        attempts = await self.repo.list_attempts_by_quiz_and_trainee(quiz_id, user_id)
        total = len(attempts)
        summaries: list[TraineeQuizAttemptSummaryOut] = []
        for index, attempt in enumerate(attempts):
            attempt_number = total - index
            summaries.append(
                TraineeQuizAttemptSummaryOut(
                    attempt_id=attempt.attempt_id,
                    status=attempt.status,
                    score=attempt.score,
                    score_percent=_score_percent(attempt.score),
                    total_correct=attempt.total_correct,
                    total_skipped=attempt.total_skipped,
                    total_questions=quiz.total_questions,
                    started_at=attempt.started_at,
                    submitted_at=attempt.submitted_at,
                    attempt_label=_format_attempt_label(
                        status=attempt.status,
                        started_at=attempt.started_at,
                        submitted_at=attempt.submitted_at,
                        attempt_number=attempt_number,
                    ),
                )
            )

        return TraineeQuizAttemptListOut(
            quiz_id=quiz.quiz_id,
            node_id=node_id,
            title=quiz.title,
            attempts=summaries,
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

        active_attempt = await self.repo.get_active_attempt_by_quiz_and_trainee(
            quiz_id, user_id
        )
        if active_attempt is not None:
            raise AttemptAlreadyInProgressException(active_attempt.attempt_id)

        published_sm = await self.study_repo.get_published_study_material(node_id)
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

        result = self._build_trainee_quiz_out(
            quiz=quiz,
            attempt=attempt,
            questions=questions,
            responses_map=responses_map,
        )
        await self.session.commit()
        return result

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
            raise AttemptAbandonedException(
                node_id=attempt.node_id,
                quiz_id=attempt.quiz_id,
            )

        if request.selected_option is None:
            raise InvalidSkipPayloadException(
                "selected_option is required to record an answer."
            )

        question = await self.repo.get_question_by_id(request.question_id)
        if question is None or question.quiz_id != attempt.quiz_id:
            raise QuestionBelongsToAnotherAttemptException()

        existing = await self.repo.get_response(attempt_id, request.question_id)
        if existing is not None and existing.was_locked:
            raise QuestionAlreadyLockedException()

        is_correct = request.selected_option == question.correct_option
        was_locked = is_correct
        hint_level = existing.hint_level_reached if existing is not None else 0
        if not is_correct:
            hint_level = min(hint_level + 1, 3)

        response = await self.repo.upsert_response(
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=request.selected_option,
            is_correct=is_correct,
            hint_level_reached=hint_level,
            was_skipped=False,
            was_locked=was_locked,
        )

        questions = await self.repo.get_active_questions_by_quiz(attempt.quiz_id)
        responses_map = await self.repo.get_responses_map(attempt_id)
        resume_question_id = compute_resume_question_id(questions, responses_map)
        next_question_id: UUID | None = None
        if is_correct:
            active_questions = [q for q in questions if q.is_active]
            current_index = next(
                (
                    index
                    for index, q in enumerate(active_questions)
                    if q.question_id == request.question_id
                ),
                -1,
            )
            if current_index >= 0 and current_index + 1 < len(active_questions):
                next_question_id = active_questions[current_index + 1].question_id

        result = QuizQuestionResponseOut(
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
            next_question_id=next_question_id,
            resume_question_id=(
                request.question_id if not is_correct else resume_question_id
            ),
        )
        await self.session.commit()
        return result

    async def _finalize_skipped_responses(
        self,
        *,
        attempt_id: UUID,
        active_questions: list[QuizQuestion],
        responses_map: dict[UUID, QuizQuestionResponse],
    ) -> None:
        """Persist final skipped flags for unanswered questions at submit time."""
        for question in active_questions:
            response = responses_map.get(question.question_id)
            skipped = is_question_skipped_at_submit(question, response)
            if response is None:
                if not skipped:
                    continue
                await self.repo.upsert_response(
                    attempt_id=attempt_id,
                    question_id=question.question_id,
                    selected_option=None,
                    is_correct=None,
                    hint_level_reached=0,
                    was_skipped=True,
                    was_locked=False,
                )
                continue
            if response.was_skipped == skipped:
                continue
            await self.repo.upsert_response(
                attempt_id=attempt_id,
                question_id=question.question_id,
                selected_option=response.selected_option,
                is_correct=response.is_correct,
                hint_level_reached=response.hint_level_reached,
                was_skipped=skipped,
                was_locked=response.was_locked,
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
            raise AttemptAbandonedException(
                node_id=attempt.node_id,
                quiz_id=attempt.quiz_id,
            )

        responses = await self.repo.get_all_responses_for_attempt(attempt_id)
        active_questions = await self.repo.get_active_questions_by_quiz(attempt.quiz_id)
        responses_map = {response.question_id: response for response in responses}
        total_questions = len(active_questions)

        await self._finalize_skipped_responses(
            attempt_id=attempt_id,
            active_questions=active_questions,
            responses_map=responses_map,
        )
        responses = await self.repo.get_all_responses_for_attempt(attempt_id)
        responses_map = {response.question_id: response for response in responses}

        total_correct = sum(1 for response in responses if response.is_correct)
        total_with_hints = sum(
            1
            for response in responses
            if response.is_correct and response.hint_level_reached > 0
        )
        total_skipped = count_skipped_at_submit(active_questions, responses_map)
        score = total_correct / total_questions if total_questions > 0 else 0.0

        attempt = await self.repo.submit_attempt(
            attempt=attempt,
            score=score,
            total_correct=total_correct,
            total_with_hints=total_with_hints,
            total_skipped=total_skipped,
        )

        progress_service = TraineeProgressService(self.session)
        await progress_service.record_quiz_attempt_submission(
            trainee_id=attempt.trainee_id,
            node_id=attempt.node_id,
            space_id=attempt.space_id,
            score=score,
        )
        # record_quiz_attempt_submission can commit via downstream recompute.
        # Refresh avoids expired-attribute lazy loads during Pydantic serialization.
        await self.session.refresh(attempt)
        result = QuizAttemptOut.model_validate(attempt)
        await self.session.commit()
        return result

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

        if attempt.status == "abandoned":
            raise AttemptAbandonedException(
                node_id=attempt.node_id,
                quiz_id=attempt.quiz_id,
            )

        quiz = await self._get_quiz_for_attempt(attempt)
        questions = await self.repo.get_all_questions_by_quiz(attempt.quiz_id)
        responses_map = await self.repo.get_responses_map(attempt_id)

        return self._build_trainee_quiz_out(
            quiz=quiz,
            attempt=attempt,
            questions=questions,
            responses_map=responses_map,
        )

    async def list_archived_quizzes(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeArchivedQuizListOut:
        """List archived quizzes grouped by superseded SM version."""
        await assert_trainee_archive_context(
            self.session, node_id=node_id, user_id=user_id, role=role
        )
        if not await assert_archive_list_gate(self.session, node_id=node_id):
            return TraineeArchivedQuizListOut(node_id=node_id, groups=[])

        archived_versions = await list_trainee_archive_sm(self.session, node_id)
        groups: list[TraineeArchivedQuizGroupOut] = []
        for version in archived_versions:
            quizzes = await list_trainee_archive_quizzes(
                self.session,
                node_id,
                study_material_version_id=version.version_id,
            )
            if not quizzes:
                continue
            quiz_items: list[TraineeArchivedQuizItemOut] = []
            for quiz in quizzes:
                attempts = await self.repo.list_attempts_by_quiz_and_trainee(
                    quiz.quiz_id, user_id
                )
                best_score = None
                for attempt in attempts:
                    if attempt.score is not None:
                        pct = _score_percent(attempt.score)
                        if pct is not None and (best_score is None or pct > best_score):
                            best_score = pct
                quiz_items.append(
                    TraineeArchivedQuizItemOut(
                        quiz_id=quiz.quiz_id,
                        study_material_version_id=quiz.study_material_version_id,
                        title=quiz.title,
                        difficulty=quiz.difficulty,
                        total_questions=quiz.total_questions,
                        published_at=quiz.published_at,
                        has_trainee_attempt=len(attempts) > 0,
                        best_score_percent=best_score,
                    )
                )
            groups.append(
                TraineeArchivedQuizGroupOut(
                    study_material_version_id=version.version_id,
                    version_number=version.version_number,
                    version_label=build_version_display_label(
                        version.version_number, version.generation_type
                    ),
                    quizzes=quiz_items,
                )
            )

        return TraineeArchivedQuizListOut(node_id=node_id, groups=groups)

    async def review_archived_quiz(
        self,
        node_id: UUID,
        quiz_id: UUID,
        user_id: UUID,
        role: str,
    ) -> ArchivedQuizReviewOut:
        """Read-only review of an archived quiz with answers and explanations."""
        await assert_trainee_archive_context(
            self.session, node_id=node_id, user_id=user_id, role=role
        )
        quiz = await assert_archived_quiz_access(
            self.session, node_id=node_id, quiz_id=quiz_id
        )

        from src.api.data.repositories import (  # noqa: PLC0415
            StudyMaterialRepository,
        )

        sm_repo = StudyMaterialRepository(self.session)
        sm_version = await sm_repo.get_version_by_id(quiz.study_material_version_id)
        version_label = (
            build_version_display_label(
                sm_version.version_number, sm_version.generation_type
            )
            if sm_version is not None
            else "Previous version"
        )

        attempts = await self.repo.list_attempts_by_quiz_and_trainee(quiz_id, user_id)
        review_attempt = _pick_archive_review_attempt(attempts)

        questions = await self.repo.get_all_questions_by_quiz(quiz_id)
        responses_map: dict[UUID, QuizQuestionResponse] = {}
        if review_attempt is not None:
            responses_map = await self.repo.get_responses_map(review_attempt.attempt_id)

        attempt_submitted = (
            review_attempt is not None and review_attempt.status == "submitted"
        )
        is_partial_attempt = review_attempt is not None and review_attempt.status in (
            "abandoned",
            "in_progress",
        )
        review_questions = [
            self._build_question_out(
                q,
                responses_map.get(q.question_id),
                attempt_submitted=attempt_submitted or is_partial_attempt,
            )
            for q in questions
        ]
        # Archive review always shows correct answers and explanations
        for q_out in review_questions:
            orig = next(q for q in questions if q.question_id == q_out.question_id)
            q_out.correct_option = orig.correct_option
            q_out.explanation = orig.explanation

        return ArchivedQuizReviewOut(
            quiz_id=quiz.quiz_id,
            node_id=quiz.node_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            total_questions=quiz.total_questions,
            study_material_version_id=quiz.study_material_version_id,
            version_label=version_label,
            attempt_id=review_attempt.attempt_id if review_attempt else None,
            attempt_status=review_attempt.status if review_attempt else None,
            is_partial_attempt=is_partial_attempt,
            score_percent=(
                _score_percent(review_attempt.score) if review_attempt else None
            ),
            total_correct=review_attempt.total_correct if review_attempt else None,
            total_skipped=review_attempt.total_skipped if review_attempt else None,
            questions=review_questions,
        )
