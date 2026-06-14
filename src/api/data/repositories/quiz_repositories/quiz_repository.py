# src/api/data/repositories/content_repository/quiz_repository.py
"""
Repository for quizzes, quiz_questions, quiz_attempts, and
quiz_question_responses DB operations.

Handles:
  - Quiz lookups (by id, all by node ordered newest first)
  - Quiz insert, publish
  - Question lookups (by id, all by quiz, active by quiz)
  - Question insert, partial update, soft-delete, bulk reorder
  - total_questions counter increment / decrement
  - Attempt lookups (by id) and insert, submit
  - Response lookups (single, all for attempt, dict map for resume)
  - Response upsert (create or update existing row)
  - Study material version lookup (for generate precondition check)
  - next order_index resolution for questions (MAX + 1)
"""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quiz_attempts import QuizAttempt
from src.api.data.models.postgres.e_learning_content.quiz_question_responses import (
    QuizQuestionResponse,
)
from src.api.data.models.postgres.e_learning_content.quiz_questions import QuizQuestion
from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.schemas.quiz_schemas.quiz_schema import QuizQuestionUpdateRequest


class QuizRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Study Material Version (precondition check) ───────────────────

    async def get_study_material_version(
        self, version_id: UUID
    ) -> StudyMaterialVersion | None:
        result = await self.db.execute(
            select(StudyMaterialVersion).where(
                StudyMaterialVersion.version_id == version_id
            )
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())

    # ── Quiz Lookups ──────────────────────────────────────────────────

    async def get_quiz_by_id(self, quiz_id: UUID) -> Quiz | None:
        result = await self.db.execute(select(Quiz).where(Quiz.quiz_id == quiz_id))
        return cast(Quiz | None, result.scalars().first())

    async def get_quizzes_by_node(self, node_id: UUID) -> list[Quiz]:
        """All quizzes for a node ordered by created_at DESC (newest first)."""
        result = await self.db.execute(
            select(Quiz).where(Quiz.node_id == node_id).order_by(Quiz.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_quizzes_for_node(self, node_id: UUID) -> int:
        """Return how many quizzes exist for a node (any publish state)."""
        result = await self.db.execute(
            select(func.count()).select_from(Quiz).where(Quiz.node_id == node_id)
        )
        return int(result.scalar() or 0)

    # ── Quiz Writes ───────────────────────────────────────────────────

    async def create_quiz(
        self,
        node_id: UUID,
        space_id: UUID,
        study_material_version_id: UUID,
        title: str,
        difficulty: str,
        created_by: UUID,
    ) -> Quiz:
        now = datetime.now(UTC)
        quiz = Quiz(
            quiz_id=uuid4(),
            node_id=node_id,
            space_id=space_id,
            study_material_version_id=study_material_version_id,
            title=title,
            total_questions=0,
            difficulty=difficulty,
            is_published=False,
            published_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(quiz)
        await self.db.commit()
        await self.db.refresh(quiz)
        return quiz

    async def publish_quiz(self, quiz: Quiz, published_by: UUID) -> Quiz:  # noqa: ARG002
        """Set is_published=True and published_at."""
        now = datetime.now(UTC)
        quiz.is_published = True
        quiz.published_at = now
        quiz.updated_at = now
        await self.db.commit()
        await self.db.refresh(quiz)
        return quiz

    async def increment_total_questions(self, quiz: Quiz) -> None:
        quiz.total_questions = (quiz.total_questions or 0) + 1
        quiz.updated_at = datetime.now(UTC)
        await self.db.commit()

    async def decrement_total_questions(self, quiz: Quiz) -> None:
        quiz.total_questions = max((quiz.total_questions or 1) - 1, 0)
        quiz.updated_at = datetime.now(UTC)
        await self.db.commit()

    # ── Question Lookups ──────────────────────────────────────────────

    async def get_question_by_id(self, question_id: UUID) -> QuizQuestion | None:
        result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.question_id == question_id)
        )
        return cast(QuizQuestion | None, result.scalars().first())

    async def get_questions_by_quiz(self, quiz_id: UUID) -> list[QuizQuestion]:
        """All questions (active and inactive) for a quiz, ordered by order_index."""
        result = await self.db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_active_questions_by_quiz(self, quiz_id: UUID) -> list[QuizQuestion]:
        """Only is_active=True questions for a quiz, ordered by order_index."""
        result = await self.db.execute(
            select(QuizQuestion)
            .where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                )
            )
            .order_by(QuizQuestion.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_active_question_count(self, quiz_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                )
            )
        )
        return result.scalar() or 0

    async def get_next_question_order_index(self, quiz_id: UUID) -> int:
        """Return MAX(order_index) + 1 among active questions. Returns 0 if none."""
        result = await self.db.execute(
            select(func.max(QuizQuestion.order_index)).where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                )
            )
        )
        max_index = result.scalar()
        return (max_index + 1) if max_index is not None else 0

    # ── Question Writes ───────────────────────────────────────────────

    async def create_question(
        self,
        quiz_id: UUID,
        node_id: UUID,
        question_text: str,
        option_a: str,
        option_b: str,
        option_c: str | None,
        option_d: str | None,
        correct_option: str,
        hint_1: str | None,
        hint_2: str | None,
        hint_3: str | None,
        explanation: str | None,
        order_index: int,
        source: str,
    ) -> QuizQuestion:
        question = QuizQuestion(
            question_id=uuid4(),
            quiz_id=quiz_id,
            node_id=node_id,
            question_text=question_text,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_option=correct_option,
            hint_1=hint_1,
            hint_2=hint_2,
            hint_3=hint_3,
            explanation=explanation,
            order_index=order_index,
            is_active=True,
            source=source,
        )
        self.db.add(question)
        await self.db.commit()
        await self.db.refresh(question)
        return question

    async def update_question(
        self, question: QuizQuestion, request: QuizQuestionUpdateRequest
    ) -> QuizQuestion:
        """Partial merge — only fields present in model_fields_set are written."""
        for field in request.model_fields_set:
            value = getattr(request, field)
            setattr(question, field, value)
        await self.db.commit()
        await self.db.refresh(question)
        return question

    async def soft_delete_question(self, question: QuizQuestion) -> None:
        question.is_active = False
        await self.db.commit()

    async def bulk_update_question_order(self, order_map: dict[UUID, int]) -> None:
        """Update order_index for multiple questions in one transaction."""
        for question_id, order_index in order_map.items():
            await self.db.execute(
                update(QuizQuestion)
                .where(QuizQuestion.question_id == question_id)
                .values(order_index=order_index)
            )
        await self.db.commit()

    # ── Attempt Lookups ───────────────────────────────────────────────

    async def get_attempt_by_id(self, attempt_id: UUID) -> QuizAttempt | None:
        result = await self.db.execute(
            select(QuizAttempt).where(QuizAttempt.attempt_id == attempt_id)
        )
        return cast(QuizAttempt | None, result.scalars().first())

    # ── Attempt Writes ────────────────────────────────────────────────

    async def create_attempt(
        self,
        quiz_id: UUID,
        node_id: UUID,
        space_id: UUID,
        trainee_id: UUID,
    ) -> QuizAttempt:
        now = datetime.now(UTC)
        attempt = QuizAttempt(
            attempt_id=uuid4(),
            quiz_id=quiz_id,
            node_id=node_id,
            space_id=space_id,
            trainee_id=trainee_id,
            status="in_progress",
            score=None,
            total_correct=None,
            total_with_hints=None,
            total_skipped=None,
            started_at=now,
            submitted_at=None,
        )
        self.db.add(attempt)
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt

    async def submit_attempt(
        self,
        attempt: QuizAttempt,
        score: float,
        total_correct: int,
        total_with_hints: int,
        total_skipped: int,
    ) -> QuizAttempt:
        now = datetime.now(UTC)
        attempt.status = "submitted"
        attempt.score = score
        attempt.total_correct = total_correct
        attempt.total_with_hints = total_with_hints
        attempt.total_skipped = total_skipped
        attempt.submitted_at = now
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt

    # ── Response Lookups ──────────────────────────────────────────────

    async def get_response(
        self, attempt_id: UUID, question_id: UUID
    ) -> QuizQuestionResponse | None:
        result = await self.db.execute(
            select(QuizQuestionResponse).where(
                and_(
                    QuizQuestionResponse.attempt_id == attempt_id,
                    QuizQuestionResponse.question_id == question_id,
                )
            )
        )
        return cast(QuizQuestionResponse | None, result.scalars().first())

    async def get_all_responses_for_attempt(
        self, attempt_id: UUID
    ) -> list[QuizQuestionResponse]:
        result = await self.db.execute(
            select(QuizQuestionResponse).where(
                QuizQuestionResponse.attempt_id == attempt_id
            )
        )
        return list(result.scalars().all())

    async def get_responses_map(
        self, attempt_id: UUID
    ) -> dict[UUID, QuizQuestionResponse]:
        """Return {question_id: response} for use in attempt resume (EC-7)."""
        rows = await self.get_all_responses_for_attempt(attempt_id)
        return {r.question_id: r for r in rows}

    # ── Response Writes ───────────────────────────────────────────────

    async def upsert_response(
        self,
        attempt_id: UUID,
        question_id: UUID,
        selected_option: str | None,
        is_correct: bool | None,
        hint_level_reached: int,
        was_skipped: bool,
        was_locked: bool,
    ) -> QuizQuestionResponse:
        """Create a new response row or update the existing one for this question."""
        existing = await self.get_response(attempt_id, question_id)
        now = datetime.now(UTC)
        attempt = await self.get_attempt_by_id(attempt_id)
        if attempt is None:
            raise ValueError("Attempt not found")

        if existing is not None:
            existing.selected_option = selected_option
            existing.is_correct = is_correct
            existing.hint_level_reached = hint_level_reached
            existing.was_skipped = was_skipped
            existing.was_locked = was_locked
            existing.responded_at = now
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        response = QuizQuestionResponse(
            response_id=uuid4(),
            attempt_id=attempt_id,
            question_id=question_id,
            trainee_id=attempt.trainee_id,
            selected_option=selected_option,
            is_correct=is_correct,
            hint_level_reached=hint_level_reached,
            was_skipped=was_skipped,
            was_locked=was_locked,
            responded_at=now,
        )
        self.db.add(response)
        await self.db.commit()
        await self.db.refresh(response)
        return response
