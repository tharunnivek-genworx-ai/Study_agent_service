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

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.quiz_exceptions.hint_generation_exceptions import (
    HintGenerationFailedException,
    HintQuestionsNotFoundException,
    HintsAlreadyCompleteException,
    HintsCannotGenerateOnPublishedQuizException,
    HintsNothingToDeleteException,
    QuizHasNoQuestionsException,
)
from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizNotFoundException,
)
from src.api.data.repositories.quiz_repositories.hint_repository import HintRepository
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.schemas.quiz_schemas.hint_schema import (
    HintGenerateRequest,
    HintRegenerateRequest,
)
from src.api.schemas.quiz_schemas.quiz_schema import QuizOut, QuizQuestionOut
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.quiz_utils.hints_status import compute_hints_status
from src.api.utils.quiz_utils.study_material_link import (
    validate_quiz_linked_version_is_published,
)
from src.api.utils.space_node_utils.node_role_assert import _assert_mentor


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
        await validate_quiz_linked_version_is_published(
            sm_repo,
            node_id=node_id,
            study_material_version_id=quiz.study_material_version_id,
        )
        return repo, quiz

    async def _build_quiz_out(self, quiz_id: UUID, quiz) -> QuizOut:  # type: ignore[no-untyped-def]
        """Build a QuizOut from the updated quiz after hint generation."""
        quiz_repo = QuizRepository(self.session)
        questions = await quiz_repo.get_questions_by_quiz(quiz_id)
        active_questions = await quiz_repo.get_active_questions_by_quiz(quiz_id)
        quiz_out = QuizOut.model_validate(quiz)
        quiz_out.questions = [QuizQuestionOut.model_validate(q) for q in questions]
        quiz_out.hints_status = compute_hints_status(active_questions)
        return quiz_out

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

        from src.api.control.agents.hint_generation_graph import (
            get_hint_generation_graph,  # noqa: PLC0415
        )

        graph = get_hint_generation_graph()
        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "quiz_id": quiz_id,
        }

        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"session": self.session}},
        )

        if final_state.get("error"):
            raise HintGenerationFailedException(str(final_state["error"]))

        quiz_repo = QuizRepository(self.session)
        updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
        return await self._build_quiz_out(quiz_id, updated_quiz)

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

        from src.api.control.agents.hint_generation_graph import (
            get_hint_generation_graph,  # noqa: PLC0415
        )

        graph = get_hint_generation_graph()
        initial_state = {
            "mentor_id": user_id,
            "node_id": node_id,
            "quiz_id": quiz_id,
            "questions_filter_ids": request.question_ids,
            "mentor_feedback": request.mentor_feedback,
        }

        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"session": self.session}},
        )

        if final_state.get("error"):
            raise HintGenerationFailedException(str(final_state["error"]))

        quiz_repo = QuizRepository(self.session)
        updated_quiz = await quiz_repo.get_quiz_by_id(quiz_id)
        return await self._build_quiz_out(quiz_id, updated_quiz)

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
