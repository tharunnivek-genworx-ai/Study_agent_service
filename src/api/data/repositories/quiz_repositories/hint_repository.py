# src/api/data/repositories/quiz_repositories/hint_repository.py
"""
Repository for hint writes on existing quiz_questions rows.

Hint generation assumes questions already exist on a persisted quiz.
This repository handles lookups for questions needing hints and bulk
hint updates — it does not create quiz or question rows.
"""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quiz_questions import QuizQuestion
from src.api.data.models.postgres.e_learning_content.quizzes import Quiz


class HintRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Quiz lookups (precondition checks) ────────────────────────────

    async def get_quiz_by_id(self, quiz_id: UUID) -> Quiz | None:
        result = await self.db.execute(select(Quiz).where(Quiz.quiz_id == quiz_id))
        return cast(Quiz | None, result.scalars().first())

    # ── Question lookups ──────────────────────────────────────────────

    async def get_active_questions_by_quiz(self, quiz_id: UUID) -> list[QuizQuestion]:
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

    async def get_active_questions_missing_hints(
        self, quiz_id: UUID
    ) -> list[QuizQuestion]:
        """Active questions where at least one hint field is NULL."""
        result = await self.db.execute(
            select(QuizQuestion)
            .where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                    or_(
                        QuizQuestion.hint_1.is_(None),
                        QuizQuestion.hint_2.is_(None),
                        QuizQuestion.hint_3.is_(None),
                    ),
                )
            )
            .order_by(QuizQuestion.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_active_questions_with_complete_hints(
        self, quiz_id: UUID
    ) -> list[QuizQuestion]:
        """Active questions where hint_1, hint_2, and hint_3 are all populated."""
        result = await self.db.execute(
            select(QuizQuestion)
            .where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                    QuizQuestion.hint_1.isnot(None),
                    QuizQuestion.hint_2.isnot(None),
                    QuizQuestion.hint_3.isnot(None),
                )
            )
            .order_by(QuizQuestion.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_active_questions_by_ids(
        self, quiz_id: UUID, question_ids: list[UUID]
    ) -> list[QuizQuestion]:
        result = await self.db.execute(
            select(QuizQuestion).where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                    QuizQuestion.question_id.in_(question_ids),
                )
            )
        )
        return list(result.scalars().all())

    # ── Hint writes ───────────────────────────────────────────────────

    async def bulk_update_question_hints(
        self,
        updates: list[tuple[UUID, str, str, str]],
    ) -> None:
        """Update hint_1/2/3 for multiple questions in one transaction."""
        if not updates:
            return

        question_ids = [question_id for question_id, _, _, _ in updates]
        result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.question_id.in_(question_ids))
        )
        questions_by_id = {q.question_id: q for q in result.scalars().all()}

        for question_id, hint_1, hint_2, hint_3 in updates:
            question = questions_by_id.get(question_id)
            if question is None:
                continue
            question.hint_1 = hint_1
            question.hint_2 = hint_2
            question.hint_3 = hint_3

        await self.db.flush()

    def _deep_merge_hint_generation(
        self,
        existing: dict[str, Any] | None,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in patch.items():
            if key == "questionErrors" and isinstance(value, list):
                by_id: dict[str, dict[str, Any]] = {}
                for err in merged.get("questionErrors") or []:
                    if not isinstance(err, dict):
                        continue
                    qid = str(err.get("questionId") or err.get("question_id"))
                    by_id[qid] = err
                for err in value:
                    if not isinstance(err, dict):
                        continue
                    qid = str(err.get("questionId") or err.get("question_id"))
                    by_id[qid] = err
                merged["questionErrors"] = list(by_id.values())
            else:
                merged[key] = value
        return merged

    async def merge_quiz_qc_result(
        self,
        quiz_id: UUID,
        patch: dict[str, Any],
        *,
        next_llm_retry_at: datetime | None = None,
    ) -> None:
        """Read-merge-write quizzes.qc_result, deep-merging hintGeneration."""
        quiz = await self.get_quiz_by_id(quiz_id)
        if quiz is None:
            return

        existing: dict[str, Any] = (
            dict(quiz.qc_result) if isinstance(quiz.qc_result, dict) else {}
        )
        hint_patch = patch.get("hintGeneration")
        if isinstance(hint_patch, dict):
            existing_hint = existing.get("hintGeneration")
            existing["hintGeneration"] = self._deep_merge_hint_generation(
                existing_hint if isinstance(existing_hint, dict) else None,
                hint_patch,
            )
            patch = {k: v for k, v in patch.items() if k != "hintGeneration"}
        existing.update(patch)
        quiz.qc_result = existing
        if next_llm_retry_at is not None:
            quiz.next_llm_retry_at = next_llm_retry_at
        await self.db.flush()

    async def update_question_hints(
        self,
        question_id: UUID,
        hint_1: str,
        hint_2: str,
        hint_3: str,
        *,
        commit: bool = False,
    ) -> None:
        """Update hint fields for a single question."""
        result = await self.db.execute(
            select(QuizQuestion).where(QuizQuestion.question_id == question_id)
        )
        question = result.scalars().first()
        if question is None:
            return
        question.hint_1 = hint_1
        question.hint_2 = hint_2
        question.hint_3 = hint_3
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def clear_all_hints_for_quiz(self, quiz_id: UUID) -> int:
        """Clear hint_1/2/3 on all active questions. Returns count of rows updated."""
        result = await self.db.execute(
            select(QuizQuestion).where(
                and_(
                    QuizQuestion.quiz_id == quiz_id,
                    QuizQuestion.is_active.is_(True),
                )
            )
        )
        questions = list(result.scalars().all())
        cleared = 0
        for question in questions:
            if (
                question.hint_1 is not None
                or question.hint_2 is not None
                or question.hint_3 is not None
            ):
                question.hint_1 = None
                question.hint_2 = None
                question.hint_3 = None
                cleared += 1
        if cleared:
            now = datetime.now(UTC)
            await self.db.execute(
                update(Quiz).where(Quiz.quiz_id == quiz_id).values(updated_at=now)
            )
        await self.db.flush()
        return cleared

    async def touch_quiz_updated_at(self, quiz_id: UUID) -> None:
        await self.db.execute(
            update(Quiz)
            .where(Quiz.quiz_id == quiz_id)
            .values(updated_at=datetime.now(UTC))
        )
        await self.db.flush()
