# tests/test_hint_regenerate_all.py
"""Tests for whole-quiz hint regeneration (scope=all) schema and service guards."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.core.exceptions import HintsNothingToRegenerateException
from src.api.core.services.quiz_services.hint_service import HintService
from src.api.schemas.quiz_schemas import HintRegenerateRequest


class TestHintRegenerateRequestSchema:
    def test_selective_requires_question_ids(self) -> None:
        with pytest.raises(ValidationError, match="question_ids is required"):
            HintRegenerateRequest(scope="selective")

    def test_selective_accepts_question_ids_without_feedback(self) -> None:
        qid = uuid4()
        request = HintRegenerateRequest(scope="selective", question_ids=[qid])
        assert request.question_ids == [qid]
        assert request.mentor_feedback is None

    def test_all_scope_rejects_missing_feedback(self) -> None:
        with pytest.raises(ValidationError, match="mentor_feedback is required"):
            HintRegenerateRequest(scope="all")

    def test_all_scope_rejects_short_feedback(self) -> None:
        with pytest.raises(ValidationError, match="mentor_feedback is required"):
            HintRegenerateRequest(scope="all", mentor_feedback="too short")

    def test_all_scope_accepts_valid_feedback(self) -> None:
        request = HintRegenerateRequest(
            scope="all",
            mentor_feedback="Make every hint more subtle and less direct.",
        )
        assert request.scope == "all"
        assert request.question_ids is None


class TestHintServiceRegenerateAll:
    def test_scope_all_resolves_question_ids_with_complete_hints(self) -> None:
        async def _run() -> None:
            node_id = uuid4()
            quiz_id = uuid4()
            user_id = uuid4()
            q1_id = uuid4()
            q2_id = uuid4()

            request = HintRegenerateRequest(
                scope="all",
                mentor_feedback="Rewrite hints to be shorter and clearer.",
            )

            service = HintService(MagicMock())
            mock_quiz = MagicMock()
            mock_quiz.node_id = node_id
            mock_quiz.is_published = False

            mock_q1 = MagicMock()
            mock_q1.question_id = q1_id
            mock_q2 = MagicMock()
            mock_q2.question_id = q2_id

            mock_repo = MagicMock()
            mock_repo.get_quiz_by_id = AsyncMock(return_value=mock_quiz)
            mock_repo.get_active_questions_by_quiz = AsyncMock(
                return_value=[mock_q1, mock_q2]
            )
            mock_repo.get_active_questions_with_complete_hints = AsyncMock(
                return_value=[mock_q1, mock_q2]
            )
            mock_repo.get_active_questions_by_ids = AsyncMock(
                return_value=[mock_q1, mock_q2]
            )

            mock_node = MagicMock()
            mock_node.space_id = uuid4()

            mock_run = MagicMock()
            mock_run.request_params = {
                "node_id": str(node_id),
                "quiz_id": str(quiz_id),
                "questions_filter_ids": [str(q1_id), str(q2_id)],
                "mentor_feedback": request.mentor_feedback,
            }

            with (
                patch.object(
                    service,
                    "_get_unpublished_quiz",
                    AsyncMock(return_value=(mock_repo, mock_quiz)),
                ),
                patch(
                    "src.api.core.services.quiz_services.hint_service._get_node_and_assert_space_access",
                    AsyncMock(return_value=mock_node),
                ),
                patch.object(
                    service, "_assert_no_running_hint_generation", AsyncMock()
                ),
                patch.object(
                    service, "_start_hint_run", AsyncMock(return_value=uuid4())
                ),
                patch.object(
                    service,
                    "_run_hint_graph",
                    AsyncMock(return_value={}),
                ) as mock_run_graph,
                patch.object(
                    service, "_build_quiz_out", AsyncMock(return_value=MagicMock())
                ),
                patch(
                    "src.api.core.services.quiz_services.hint_service.QuizRepository"
                ) as mock_quiz_repo_cls,
                patch(
                    "src.api.core.services.quiz_services.hint_service.GenerationRunService"
                ) as mock_run_service_cls,
            ):
                mock_quiz_repo_cls.return_value.get_quiz_by_id = AsyncMock(
                    return_value=mock_quiz
                )
                mock_run_service_cls.return_value.acquire_lock_for_run = AsyncMock(
                    return_value=mock_run
                )
                mock_run_service_cls.return_value.store_run_result = AsyncMock()
                mock_run_service_cls.return_value.fail_run = AsyncMock()
                run_id = await service.start_regenerate_hints(
                    node_id, quiz_id, request, user_id, "mentor"
                )
                await service.execute_regenerate_hints(
                    run_id=run_id,
                    user_id=user_id,
                )

            mock_repo.get_active_questions_with_complete_hints.assert_awaited_once_with(
                quiz_id
            )
            graph_state = mock_run_graph.await_args.kwargs["initial_state"]
            assert graph_state["questions_filter_ids"] == [q1_id, q2_id]
            assert graph_state["mentor_feedback"] == request.mentor_feedback

        asyncio.run(_run())

    def test_scope_all_raises_when_no_complete_hints(self) -> None:
        async def _run() -> None:
            node_id = uuid4()
            quiz_id = uuid4()
            user_id = uuid4()

            request = HintRegenerateRequest(
                scope="all",
                mentor_feedback="Make every hint more subtle and less direct.",
            )

            service = HintService(MagicMock())
            mock_quiz = MagicMock()
            mock_repo = MagicMock()
            mock_repo.get_active_questions_by_quiz = AsyncMock(
                return_value=[MagicMock()]
            )
            mock_repo.get_active_questions_with_complete_hints = AsyncMock(
                return_value=[]
            )

            with patch.object(
                service,
                "_get_unpublished_quiz",
                AsyncMock(return_value=(mock_repo, mock_quiz)),
            ):
                with pytest.raises(HintsNothingToRegenerateException):
                    await service.start_regenerate_hints(
                        node_id, quiz_id, request, user_id, "mentor"
                    )

        asyncio.run(_run())
