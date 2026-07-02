# tests/test_question_rework_graph.py
"""End-to-end tests for mentor question rework (quiz single-regen graph)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.control.hint_agent.nodes.hint_nodes import load_hint_context
from src.api.control.quiz_agent.graph.quiz_graph.quiz_generation_graph import (
    build_quiz_generation_graph,
    reset_quiz_generation_graph,
)
from src.api.control.quiz_agent.graph.quiz_graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)
from src.api.control.quiz_agent.nodes.quiz_graph import (
    deterministic_validate_question_patches,
    invoke_quiz_single_regen_llm,
    parse_quiz_single_regen_output,
    persist_question_patches,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository


def _sample_question_dict(*, question_id: str, order_index: int = 0) -> dict:
    return {
        "question_id": question_id,
        "question_text": "What is encapsulation?",
        "option_a": "Hiding data",
        "option_b": "Inheritance",
        "option_c": "Polymorphism",
        "option_d": "Abstraction",
        "correct_option": "A",
        "explanation": "Encapsulation hides internal state.",
        "order_index": order_index,
    }


def _sample_llm_patch(*, question_id: str) -> dict:
    return {
        "question_id": question_id,
        "question_text": "Which OOP principle hides internal state?",
        "option_a": "Hiding data",
        "option_b": "Inheritance",
        "option_c": "Polymorphism",
        "option_d": "Abstraction",
        "correct_option": "A",
        "explanation": "Encapsulation bundles data with methods that operate on it.",
        "hints_stale": True,
    }


def _llm_result(*, content: str, ok: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        ok=ok,
        content=content,
        error_type=None if ok else "rate_limit",
        provider_meta=None,
        next_llm_retry_at=None,
        model="llama-3.3-70b-versatile",
        token_usage=42,
    )


class TestQuestionReworkGraphPipeline:
    def test_mock_llm_through_persist_clears_hints(self) -> None:
        async def _run() -> None:
            question_id = uuid4()
            quiz_id = uuid4()
            qid_str = str(question_id)

            llm_output = json.dumps([_sample_llm_patch(question_id=qid_str)])
            state = {
                "quiz_id": quiz_id,
                "question_ids": [question_id],
                "all_questions": [_sample_question_dict(question_id=qid_str)],
                "prompt_input": {
                    "system_prompt": "system",
                    "user_message": "user",
                },
            }

            with patch(
                "src.api.control.quiz_agent.nodes.quiz_graph.invoke_quiz_single_regen_llm_node.call_quiz_llm",
                AsyncMock(return_value=_llm_result(content=llm_output)),
            ):
                invoke_state = await invoke_quiz_single_regen_llm(state)  # type: ignore[arg-type]

            assert invoke_state.get("raw_llm_output") == llm_output
            assert invoke_state.get("terminal_llm_failure") is False

            parse_state = await parse_quiz_single_regen_output(
                {**state, **invoke_state}  # type: ignore[arg-type]
            )
            assert parse_state.get("error") is None
            assert parse_state.get("parsed_patches")
            assert parse_state.get("hints_stale_question_ids") == [qid_str]

            validate_update = await deterministic_validate_question_patches(
                {**state, **invoke_state, **parse_state}  # type: ignore[arg-type]
            )
            assert validate_update.get("struct_validation_passed") is True
            assert validate_update.get("validated_patches")

            mock_repo = MagicMock()
            mock_repo.patch_questions_from_ai = AsyncMock(return_value=[qid_str])
            config = {"configurable": {"session": MagicMock()}}

            with patch(
                "src.api.control.quiz_agent.nodes.quiz_graph.persist_question_patches_node.QuizRepository",
                return_value=mock_repo,
            ):
                persist_state = await persist_question_patches(
                    {
                        **state,
                        **invoke_state,
                        **parse_state,
                        **validate_update,
                    },  # type: ignore[arg-type]
                    config,  # type: ignore[arg-type]
                )

            mock_repo.patch_questions_from_ai.assert_awaited_once()
            call_args = mock_repo.patch_questions_from_ai.await_args
            assert call_args.args[0] == quiz_id
            patches = call_args.args[1]
            assert patches[0]["question_id"] == qid_str
            assert patches[0]["question_text"].startswith("Which OOP principle")
            assert persist_state.get("hints_stale_question_ids") == [qid_str]

        asyncio.run(_run())

    def test_parse_rejects_vague_feedback_response(self) -> None:
        async def _run() -> None:
            question_id = uuid4()
            vague_output = json.dumps(
                {
                    "rework_status": "vague",
                    "message": "Feedback too vague to apply.",
                }
            )
            state = {
                "question_ids": [question_id],
                "raw_llm_output": vague_output,
            }
            result = await parse_quiz_single_regen_output(state)  # type: ignore[arg-type]
            assert result.get("rework_status") == "vague"
            assert result.get("error") == "Feedback too vague to apply."
            assert result.get("parsed_patches") is None

        asyncio.run(_run())


class TestPatchQuestionsFromAi:
    def test_clears_hints_on_patched_rows(self) -> None:
        async def _run() -> None:
            quiz_id = uuid4()
            question_id = uuid4()

            mock_question = MagicMock()
            mock_question.question_id = question_id
            mock_question.quiz_id = quiz_id
            mock_question.is_active = True
            mock_question.hint_1 = "old hint 1"
            mock_question.hint_2 = "old hint 2"
            mock_question.hint_3 = "old hint 3"

            mock_quiz = MagicMock()
            mock_db = MagicMock()
            mock_db.flush = AsyncMock()
            mock_db.commit = AsyncMock()

            repo = QuizRepository(mock_db)
            repo.get_question_by_id = AsyncMock(return_value=mock_question)  # type: ignore[method-assign]
            repo.get_quiz_by_id = AsyncMock(return_value=mock_quiz)  # type: ignore[method-assign]

            patch_payload = _sample_llm_patch(question_id=str(question_id))

            patched_ids = await repo.patch_questions_from_ai(
                quiz_id,
                [patch_payload],
                commit=False,
            )

            assert patched_ids == [str(question_id)]
            assert mock_question.hint_1 is None
            assert mock_question.hint_2 is None
            assert mock_question.hint_3 is None
            assert mock_question.question_text == patch_payload["question_text"]
            mock_db.flush.assert_awaited()
            mock_db.commit.assert_not_awaited()

        asyncio.run(_run())


class TestUnifiedGraphQuestionReworkRouting:
    def test_question_ids_without_mode_skips_quality_check(self) -> None:
        """Fresh rework via question_ids routes through rework branch, not QC."""

        async def _run() -> list[str]:
            question_id = uuid4()
            quiz_id = uuid4()
            node_id = uuid4()
            mentor_id = uuid4()
            space_id = uuid4()
            qid_str = str(question_id)

            llm_output = json.dumps([_sample_llm_patch(question_id=qid_str)])

            mock_question = MagicMock()
            mock_question.question_id = question_id
            mock_question.question_text = "What is encapsulation?"
            mock_question.option_a = "Hiding data"
            mock_question.option_b = "Inheritance"
            mock_question.option_c = "Polymorphism"
            mock_question.option_d = "Abstraction"
            mock_question.correct_option = "A"
            mock_question.explanation = "Encapsulation hides internal state."
            mock_question.order_index = 0

            mock_quiz = MagicMock()
            mock_quiz.node_id = node_id
            mock_quiz.is_published = False
            mock_quiz.difficulty = "medium"

            mock_repo = MagicMock()
            mock_repo.get_quiz_by_id = AsyncMock(return_value=mock_quiz)
            mock_repo.get_active_questions_by_quiz = AsyncMock(
                return_value=[mock_question]
            )
            mock_repo.patch_questions_from_ai = AsyncMock(return_value=[qid_str])

            mock_node = MagicMock()
            mock_node.space_id = space_id
            mock_node.title = "OOP Principles"

            active_version = SimpleNamespace(
                version_id=uuid4(),
                content="Study material on encapsulation and OOP.",
                concept_plan=None,
            )
            mock_study_repo = MagicMock()
            mock_study_repo.get_published_version = AsyncMock(return_value=None)
            mock_study_repo.get_active_version = AsyncMock(return_value=active_version)
            mock_study_repo.get_latest_workspace_draft = AsyncMock(return_value=None)

            initial_state = {
                "node_id": node_id,
                "quiz_id": quiz_id,
                "mentor_id": mentor_id,
                "question_ids": [question_id],
                "mentor_feedback": "Make distractors harder.",
            }
            config = {"configurable": {"session": MagicMock()}}

            reset_quiz_generation_graph()
            graph = build_quiz_generation_graph()
            visited_nodes: list[str] = []

            with (
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node._get_node_and_assert_space_access",
                    AsyncMock(return_value=mock_node),
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node.StudyMaterialRepository",
                    return_value=mock_study_repo,
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.load_quiz_single_regen_context_node.QuizRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.persist_question_patches_node.QuizRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.invoke_quiz_single_regen_llm_node.call_quiz_llm",
                    AsyncMock(return_value=_llm_result(content=llm_output)),
                ),
            ):
                async for chunk in graph.astream(
                    initial_state,
                    config,
                    stream_mode="updates",
                ):
                    visited_nodes.extend(chunk.keys())

            return visited_nodes

        visited = asyncio.run(_run())

        assert "quality_check" not in visited
        assert "persist_question_patches" in visited
        assert visited[-1] == "persist_question_patches"
        assert "load_quiz_single_regen_context" in visited
        assert "load_generation_context" not in visited
        assert "quiz_generator" not in visited


class TestQuizSingleRegenResumeRouter:
    def test_resume_after_invoke_routes_to_parse(self) -> None:
        state = {
            "mode": "improve",
            "raw_llm_output": '[{"question_id": "q1"}]',
        }
        assert (
            resolve_resume_next_node(
                state, last_completed_node="invoke_quiz_single_regen_llm"
            )
            == "parse_quiz_single_regen_output"
        )

    def test_resume_after_validate_routes_to_persist(self) -> None:
        state = {
            "mode": "improve",
            "validated_patches": [_sample_llm_patch(question_id="q1")],
        }
        assert (
            resolve_resume_next_node(
                state,
                last_completed_node="deterministic_validate_question_patches",
            )
            == "persist_question_patches"
        )

    def test_hydrate_checkpoint_restores_question_ids(self) -> None:
        node_id = uuid4()
        quiz_id = uuid4()
        question_id = uuid4()
        state = hydrate_checkpoint_state(
            {},
            last_completed_node="build_quiz_single_regen_prompt",
            request_params={
                "node_id": str(node_id),
                "quiz_id": str(quiz_id),
                "question_ids": [str(question_id)],
                "mentor_feedback": "Make distractors harder.",
            },
        )
        assert state["node_id"] == node_id
        assert state["quiz_id"] == quiz_id
        assert state["question_ids"] == [question_id]
        assert state["mentor_feedback"] == "Make distractors harder."


class TestLoadHintContextPreviousHints:
    def test_regeneration_includes_previous_hints(self) -> None:
        async def _run() -> None:
            node_id = uuid4()
            quiz_id = uuid4()
            mentor_id = uuid4()
            question_id = uuid4()

            mock_question = MagicMock()
            mock_question.question_id = question_id
            mock_question.question_text = "What is 2+2?"
            mock_question.option_a = "3"
            mock_question.option_b = "4"
            mock_question.option_c = "5"
            mock_question.option_d = "6"
            mock_question.correct_option = "B"
            mock_question.explanation = "Basic math."
            mock_question.hint_1 = "Count up."
            mock_question.hint_2 = "Pairs."
            mock_question.hint_3 = "Two twos."

            mock_quiz = MagicMock()
            mock_quiz.node_id = node_id
            mock_quiz.is_published = False
            mock_quiz.study_material_version_id = None

            mock_repo = MagicMock()
            mock_repo.get_quiz_by_id = AsyncMock(return_value=mock_quiz)
            mock_repo.get_active_questions_by_ids = AsyncMock(
                return_value=[mock_question]
            )

            mock_node = MagicMock()
            mock_node.space_id = uuid4()
            mock_node.title = "Arithmetic"

            config = {"configurable": {"session": MagicMock()}}
            state = {
                "node_id": node_id,
                "quiz_id": quiz_id,
                "mentor_id": mentor_id,
                "questions_filter_ids": [question_id],
                "mentor_feedback": "Make hints subtler.",
            }

            with (
                patch(
                    "src.api.control.hint_agent.nodes.hint_nodes._get_node_and_assert_space_access",
                    AsyncMock(return_value=mock_node),
                ),
                patch(
                    "src.api.control.hint_agent.nodes.hint_nodes.HintRepository",
                    return_value=mock_repo,
                ),
            ):
                result = await load_hint_context(state, config)  # type: ignore[arg-type]

            questions = result.get("questions_for_hinting") or []
            assert len(questions) == 1
            assert questions[0]["previous_hints"] == {
                "hint_1": "Count up.",
                "hint_2": "Pairs.",
                "hint_3": "Two twos.",
            }

        asyncio.run(_run())
