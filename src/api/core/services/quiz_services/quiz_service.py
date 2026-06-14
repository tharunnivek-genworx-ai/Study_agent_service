# src/api/core/services/content_service/quiz_service.py
"""
Quiz service: all business logic for quizzes, quiz_questions,
quiz_attempts, and quiz_question_responses.

Flow per TDD §3.2.2 and §3.2.3:
  GENERATE     → validate ownership → validate study material version is published
                 → (LLM placeholder) → insert quizzes row + quiz_questions rows
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
    AttemptAbandonedException,
    AttemptAlreadySubmittedException,
    AttemptForbiddenException,
    InvalidSkipPayloadException,
    QuestionAlreadyLockedException,
    QuestionBelongsToAnotherAttemptException,
    QuizAlreadyPublishedException,
    QuizAttemptNotFoundException,
    QuizHasNoPublishedStudyMaterialException,
    QuizNotFoundException,
    QuizNotPublishedException,
    QuizQuestionNotFoundException,
    StudyMaterialVersionMismatchException,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.schemas.quiz_schemas.quiz_schema import (
    CorrectOption,
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizGenerateRequest,
    QuizListOut,
    QuizOut,
    QuizPublishRequest,
    QuizQuestionCreateRequest,
    QuizQuestionDeletedOut,
    QuizQuestionOut,
    QuizQuestionReorderRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    QuizQuestionUpdateRequest,
    QuizSummaryOut,
    TraineeQuizOut,
    TraineeQuizQuestionOut,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
)

_TRAINEE_ROLE = "trainee"


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

    # ── generate ───────────────────────────────────────────────────────

    async def generate_quiz(
        self,
        node_id: UUID,
        request: QuizGenerateRequest,
        user_id: UUID,
        role: str,
    ) -> str:
        """Placeholder — Quiz Agent LLM pipeline not yet implemented.

        Validates ownership and study material version preconditions;
        returns a stub string. In production this will persist a quizzes
        row and quiz_questions rows after the LLM call.
        """
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)

        # Validate study material version exists and is published (EC-4)
        version = await repo.get_study_material_version(
            request.study_material_version_id
        )
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_published:
            raise QuizHasNoPublishedStudyMaterialException()

        # LLM call goes here — placeholder for now
        return "AI response"

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
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
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
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if quiz.is_published:
            raise QuizAlreadyPublishedException()

        quiz = await repo.publish_quiz(quiz, published_by=user_id)
        questions = await repo.get_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        return quiz_out

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
        await repo.increment_total_questions(quiz)

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

        question = await repo.get_question_by_id(question_id)
        if question is None or question.quiz_id != quiz_id or not question.is_active:
            raise QuizQuestionNotFoundException()

        await repo.soft_delete_question(question)
        await repo.decrement_total_questions(quiz)

        return QuizQuestionDeletedOut(question_id=question_id)

    # ── attempt lifecycle ──────────────────────────────────────────────

    async def start_attempt(
        self,
        node_id: UUID,
        quiz_id: UUID,
        request: QuizAttemptStartRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,
    ) -> TraineeQuizOut:
        """Create a new attempt and return the full question set with blank state.

        EC-9: multiple attempts are always allowed.
        """
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = QuizRepository(self.session)
        quiz = await repo.get_quiz_by_id(quiz_id)
        if quiz is None or quiz.node_id != node_id:
            raise QuizNotFoundException()
        if not quiz.is_published:
            raise QuizNotPublishedException()

        attempt = await repo.create_attempt(
            quiz_id=quiz_id,
            node_id=node_id,
            space_id=node.space_id,
            trainee_id=user_id,
        )

        questions = await repo.get_active_questions_by_quiz(quiz_id)
        trainee_questions = [
            TraineeQuizQuestionOut(
                question_id=q.question_id,
                question_text=q.question_text,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
                is_active=q.is_active,
                order_index=q.order_index,
                hint_1=None,
                hint_2=None,
                hint_3=None,
                hint_level_reached=0,
                was_skipped=False,
                was_locked=False,
                selected_option=None,
                is_correct=None,
            )
            for q in questions
        ]

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
        """Record or update a trainee's response for a single question.

        - was_skipped=True + selected_option=None → deliberate skip (EC-8).
        - Correct answer → was_locked=True (EC-7).
        - Wrong answer   → hint_level_reached incremented, next hint revealed.
        """
        repo = QuizRepository(self.session)
        attempt = await repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        if attempt.status == "submitted":
            raise AttemptAlreadySubmittedException()
        if attempt.status == "abandoned":
            raise AttemptAbandonedException()

        # Skip guard (EC-8)
        if request.was_skipped and request.selected_option is not None:
            raise InvalidSkipPayloadException()

        # Validate question belongs to this quiz
        question = await repo.get_question_by_id(request.question_id)
        if question is None or question.quiz_id != attempt.quiz_id:
            raise QuestionBelongsToAnotherAttemptException()

        # Check for existing response to detect lock
        existing = await repo.get_response(attempt_id, request.question_id)
        if existing is not None and existing.was_locked:
            raise QuestionAlreadyLockedException()

        # Evaluate answer
        is_correct: bool | None = None
        was_locked = False
        hint_level = existing.hint_level_reached if existing is not None else 0

        if not request.was_skipped and request.selected_option is not None:
            is_correct = request.selected_option == question.correct_option
            if is_correct:
                was_locked = True
            else:
                hint_level = min(hint_level + 1, 3)

        response = await repo.upsert_response(
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=request.selected_option,
            is_correct=is_correct,
            hint_level_reached=hint_level,
            was_skipped=request.was_skipped,
            was_locked=was_locked,
        )

        # Progressive hint reveal
        hint_1 = question.hint_1 if hint_level >= 1 else None
        hint_2 = question.hint_2 if hint_level >= 2 else None
        hint_3 = question.hint_3 if hint_level >= 3 else None

        return QuizQuestionResponseOut(
            response_id=response.response_id,
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=response.selected_option,
            is_correct=response.is_correct,
            hint_level_reached=hint_level,
            was_skipped=response.was_skipped,
            was_locked=response.was_locked,
            hint_1=hint_1,
            hint_2=hint_2,
            hint_3=hint_3,
        )

    async def submit_attempt(
        self,
        attempt_id: UUID,
        request: QuizAttemptSubmitRequest,  # noqa: ARG002
        user_id: UUID,
        role: str,  # noqa: ARG002
    ) -> QuizAttemptOut:
        """Compute score and mark attempt as submitted.

        Engagement & Chat Service is notified separately (stub) to update
        trainee_node_progress.quiz_best_score and quiz_passed.
        """
        repo = QuizRepository(self.session)
        attempt = await repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        if attempt.status == "submitted":
            raise AttemptAlreadySubmittedException()
        if attempt.status == "abandoned":
            raise AttemptAbandonedException()

        responses = await repo.get_all_responses_for_attempt(attempt_id)
        total_questions = await repo.get_active_question_count(attempt.quiz_id)

        total_correct = sum(1 for r in responses if r.is_correct)
        total_with_hints = sum(
            1 for r in responses if r.is_correct and r.hint_level_reached > 0
        )
        total_skipped = sum(1 for r in responses if r.was_skipped)
        score = total_correct / total_questions if total_questions > 0 else 0.0

        attempt = await repo.submit_attempt(
            attempt=attempt,
            score=score,
            total_correct=total_correct,
            total_with_hints=total_with_hints,
            total_skipped=total_skipped,
        )

        # TODO: notify Engagement & Chat Service of quiz completion

        return QuizAttemptOut.model_validate(attempt)

    async def get_attempt(
        self,
        attempt_id: UUID,
        user_id: UUID,
        role: str,  # noqa: ARG002
    ) -> TraineeQuizOut:
        """Resume a mid-progress attempt. Merges question + response state (EC-7)."""
        repo = QuizRepository(self.session)
        attempt = await repo.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise QuizAttemptNotFoundException()

        _assert_trainee_owns_attempt(attempt.trainee_id, user_id)

        quiz = await repo.get_quiz_by_id(attempt.quiz_id)
        if quiz is None:
            raise QuizNotFoundException()

        questions = await repo.get_questions_by_quiz(attempt.quiz_id)
        responses_map = await repo.get_responses_map(attempt_id)

        trainee_questions: list[TraineeQuizQuestionOut] = []
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
