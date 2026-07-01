# src/api/data/repositories/trainee_quiz_repositories/trainee_quiz_repository.py
"""
Repository for trainee-side quiz attempt DB operations.

Published study material reads belong in ``TraineeStudyRepository``.
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
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_HIDDEN,
)


class TraineeQuizRepository:
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

    async def get_archived_quiz_by_id(
        self, node_id: UUID, quiz_id: UUID
    ) -> Quiz | None:
        """Find an archived quiz for trainee reference review."""
        result = await self.db.execute(
            select(Quiz).where(
                and_(
                    Quiz.node_id == node_id,
                    Quiz.quiz_id == quiz_id,
                    Quiz.lifecycle_status == LIFECYCLE_ARCHIVED,
                )
            )
        )
        return cast(Quiz | None, result.scalars().first())

    async def get_quiz_by_id(self, quiz_id: UUID) -> Quiz | None:
        result = await self.db.execute(select(Quiz).where(Quiz.quiz_id == quiz_id))
        return cast(Quiz | None, result.scalars().first())

    async def get_hidden_quiz_with_trainee_attempts(
        self, node_id: UUID, trainee_id: UUID
    ) -> Quiz | None:
        """Return the newest hidden/archived quiz this trainee has attempt history on."""
        result = await self.db.execute(
            select(Quiz)
            .join(QuizAttempt, QuizAttempt.quiz_id == Quiz.quiz_id)
            .where(
                and_(
                    Quiz.node_id == node_id,
                    Quiz.lifecycle_status.in_((LIFECYCLE_HIDDEN, LIFECYCLE_ARCHIVED)),
                    QuizAttempt.trainee_id == trainee_id,
                )
            )
            .order_by(
                QuizAttempt.submitted_at.desc().nullslast(),
                QuizAttempt.started_at.desc(),
            )
            .limit(1)
        )
        return cast(Quiz | None, result.scalars().first())

    async def get_published_quiz_node_ids(self, node_ids: list[UUID]) -> set[UUID]:
        """Return node ids that currently have a published quiz."""
        if not node_ids:
            return set()
        result = await self.db.execute(
            select(Quiz.node_id).where(
                and_(
                    Quiz.node_id.in_(node_ids),
                    Quiz.is_published.is_(True),
                )
            )
        )
        return {row[0] for row in result.all()}

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

    async def list_attempts_by_quiz_and_trainee(
        self, quiz_id: UUID, trainee_id: UUID
    ) -> list[QuizAttempt]:
        """Return all attempts (any status) for a trainee, newest activity first."""
        result = await self.db.execute(
            select(QuizAttempt)
            .where(
                and_(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.trainee_id == trainee_id,
                )
            )
            .order_by(
                QuizAttempt.submitted_at.desc().nullslast(),
                QuizAttempt.started_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def count_submitted_attempts_by_quiz_and_trainee(
        self, quiz_id: UUID, trainee_id: UUID
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                and_(
                    QuizAttempt.quiz_id == quiz_id,
                    QuizAttempt.trainee_id == trainee_id,
                    QuizAttempt.status == "submitted",
                )
            )
        )
        return int(result.scalar() or 0)

    async def abandon_in_progress_attempts_for_quizzes(
        self, quiz_ids: list[UUID]
    ) -> int:
        """Abandon all in-progress attempts for the given quizzes."""
        from src.api.utils.content_lifecycle.attempt_freeze import (  # noqa: PLC0415
            abandon_in_progress_attempts_for_quizzes,
        )

        return await abandon_in_progress_attempts_for_quizzes(self.db, quiz_ids)

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
        await self.db.flush()
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
            await self.db.flush()
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
        await self.db.flush()
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
        await self.db.flush()
        await self.db.refresh(attempt)
        return attempt
