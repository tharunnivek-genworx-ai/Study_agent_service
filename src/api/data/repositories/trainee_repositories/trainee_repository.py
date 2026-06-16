# src/api/data/repositories/trainee_repositories/trainee_repository.py
"""
Repository for trainee-side quiz and study material DB operations.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
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


class TraineeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Quiz operations ──────────────────────────────────────────────

    async def get_published_quiz_by_node(self, node_id: UUID) -> Quiz | None:
        """Find the currently published quiz for a node."""
        result = await self.db.execute(
            select(Quiz).where(
                and_(
                    Quiz.node_id == node_id,
                    Quiz.is_published.is_(True),
                )
            )
        )
        return cast(Quiz | None, result.scalars().first())

    async def get_active_attempt_by_quiz_and_trainee(
        self, quiz_id: UUID, trainee_id: UUID
    ) -> QuizAttempt | None:
        """Find an in-progress attempt for a trainee on a quiz."""
        result = await self.db.execute(
            select(QuizAttempt).where(
                and_(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.trainee_id == trainee_id,
                    QuizAttempt.status == "in_progress",
                )
            )
        )
        return cast(QuizAttempt | None, result.scalars().first())

    async def get_attempt_by_id(self, attempt_id: UUID) -> QuizAttempt | None:
        """Fetch an attempt by ID."""
        result = await self.db.execute(
            select(QuizAttempt).where(QuizAttempt.attempt_id == attempt_id)
        )
        return cast(QuizAttempt | None, result.scalars().first())

    async def create_attempt(
        self,
        quiz_id: UUID,
        node_id: UUID,
        space_id: UUID,
        trainee_id: UUID,
    ) -> QuizAttempt:
        """Create a new quiz attempt."""
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

    async def get_active_questions_by_quiz(self, quiz_id: UUID) -> list[QuizQuestion]:
        """Get all active questions in a quiz ordered by order_index."""
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

    async def get_all_questions_by_quiz(self, quiz_id: UUID) -> list[QuizQuestion]:
        """Get all questions (active or not) in a quiz ordered by order_index."""
        result = await self.db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_question_by_id(self, question_id: UUID) -> QuizQuestion | None:
        """Fetch a quiz question by ID."""
        result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.question_id == question_id)
        )
        return cast(QuizQuestion | None, result.scalars().first())

    async def get_response(
        self, attempt_id: UUID, question_id: UUID
    ) -> QuizQuestionResponse | None:
        """Get trainee's response to a question in an attempt."""
        result = await self.db.execute(
            select(QuizQuestionResponse).where(
                and_(
                    QuizQuestionResponse.attempt_id == attempt_id,
                    QuizQuestionResponse.question_id == question_id,
                )
            )
        )
        return cast(QuizQuestionResponse | None, result.scalars().first())

    async def get_responses_map(
        self, attempt_id: UUID
    ) -> dict[UUID, QuizQuestionResponse]:
        """Return {question_id: response} map for an attempt."""
        rows = await self.get_all_responses_for_attempt(attempt_id)
        return {r.question_id: r for r in rows}

    async def get_all_responses_for_attempt(
        self, attempt_id: UUID
    ) -> list[QuizQuestionResponse]:
        """Get all responses for an attempt."""
        result = await self.db.execute(
            select(QuizQuestionResponse).where(
                QuizQuestionResponse.attempt_id == attempt_id
            )
        )
        return list(result.scalars().all())

    async def get_active_question_count(self, quiz_id: UUID) -> int:
        """Return count of active questions in a quiz."""
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                )
            )
        )
        return result.scalar() or 0

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
        """Create or update a response for a question in an attempt."""
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

    async def submit_attempt(
        self,
        attempt: QuizAttempt,
        score: float,
        total_correct: int,
        total_with_hints: int,
        total_skipped: int,
    ) -> QuizAttempt:
        """Mark attempt as submitted and write score/aggregations."""
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

    # ── Study material operations ────────────────────────────────────

    async def get_published_study_material(
        self, node_id: UUID
    ) -> StudyMaterialVersion | None:
        """Return the latest is_published=True study material version for a node."""
        result = await self.db.execute(
            select(StudyMaterialVersion)
            .where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
            .order_by(StudyMaterialVersion.version_number.desc())
            .limit(1)
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())
