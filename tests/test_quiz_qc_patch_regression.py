# tests/test_quiz_qc_patch_regression.py
"""Regression tests for the Uvicorn quiz QC patch loop (oopslog scenario).

Replays the production failure: 10 questions generated, QC fails on one
answer_correctness issue, patch retry must keep quiz at 10 questions and route
as question_patch — never full_regeneration accumulation.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.control.quiz_agent.graph.quiz_graph.quiz_generation_graph import (
    _route_after_deterministic_validate,
    _route_after_quality_check,
    _route_after_quiz_generator,
    build_quiz_generation_graph,
    reset_quiz_generation_graph,
)
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)
from src.api.utils.quiz_utils.quality_check_utils.document.question_merge import (
    merge_full_regeneration_preserving_passing,
    prepare_question_patches_for_merge,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_retry_routing import (
    classify_quiz_retry_routing,
)

FAILED_QUESTION_ID = "c0602269-b85a-4b91-b1db-bd821dd6f3da"

INITIAL_GENERATION_JSON = """[
  {"question_text": "What is the primary purpose of Uvicorn?", "option_a": "To provide a web framework for building applications", "option_b": "To serve as a database management system", "option_c": "To act as a lightning-fast ASGI server for running asynchronous Python web applications", "option_d": "To offer a front-end development tool", "correct_option": "C", "explanation": "Uvicorn is designed to be a lightning-fast ASGI server.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Introduction to Uvicorn"},
  {"question_text": "How do you install Uvicorn?", "option_a": "Using a package manager like npm", "option_b": "Using a package manager like pip", "option_c": "By downloading the source code and compiling it manually", "option_d": "By using a cloud-based installation service", "correct_option": "B", "explanation": "Uvicorn can be installed using pip.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Installing and Running Uvicorn"},
  {"question_text": "What is the purpose of the workers parameter in Uvicorn configuration?", "option_a": "To specify the number of CPU cores to use", "option_b": "To specify the amount of memory to allocate", "option_c": "To specify the number of worker processes to use", "option_d": "To specify the log level", "correct_option": "C", "explanation": "The workers parameter specifies worker processes.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Configuring Uvicorn"},
  {"question_text": "Which of the following frameworks can be used with Uvicorn?", "option_a": "Django", "option_b": "Flask", "option_c": "FastAPI and Starlette", "option_d": "Ruby on Rails", "correct_option": "C", "explanation": "Uvicorn works with FastAPI and Starlette.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Uvicorn with Frameworks"},
  {"question_text": "How do you enable the built-in debugger in Uvicorn?", "option_a": "By setting the debug parameter to False", "option_b": "By setting the debug parameter to True", "option_c": "By using a third-party debugging tool", "option_d": "By setting the log_level parameter to debug", "correct_option": "B", "explanation": "Set debug to True.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Debugging and Logging"},
  {"question_text": "What is the purpose of the log_level parameter in Uvicorn configuration?", "option_a": "To specify the number of worker processes to use", "option_b": "To specify the amount of memory to allocate", "option_c": "To specify the log level", "option_d": "To specify the host and port to bind to", "correct_option": "C", "explanation": "log_level controls logging verbosity.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Debugging and Logging"},
  {"question_text": "What is the benefit of using Uvicorn with a framework like FastAPI?", "option_a": "Improved performance and scalability", "option_b": "Simplified development and deployment", "option_c": "Enhanced security features", "option_d": "All of the above", "correct_option": "A", "explanation": "Uvicorn with FastAPI improves performance and scalability.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Uvicorn with Frameworks"},
  {"question_text": "How do you run a Uvicorn application?", "option_a": "Using the uvicorn.run function", "option_b": "Using the uvicorn.start function", "option_c": "Using the uvicorn.stop function", "option_d": "Using the uvicorn.restart function", "correct_option": "A", "explanation": "Use uvicorn.run.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Installing and Running Uvicorn"},
  {"question_text": "What is the purpose of the host parameter in Uvicorn configuration?", "option_a": "To specify the number of worker processes to use", "option_b": "To specify the log level", "option_c": "To specify the host and port to bind to", "option_d": "To specify the amount of memory to allocate", "correct_option": "C", "explanation": "host sets bind address.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Configuring Uvicorn"},
  {"question_text": "What is the benefit of using Uvicorn's built-in logging features?", "option_a": "Improved performance and scalability", "option_b": "Simplified development and deployment", "option_c": "Enhanced security features", "option_d": "Easier debugging and troubleshooting", "correct_option": "D", "explanation": "Logging aids debugging.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Debugging and Logging"}
]"""

QC_VERIFICATION_JSON = {
    "question_results": [
        {
            "question_id": FAILED_QUESTION_ID,
            "question_number": 7,
            "answer_correctness_passed": False,
            "answer_evidence": "Independent answer: D. Marked option A does not match.",
            "quality_passed": True,
            "quality_evidence": "Clear stem.",
            "corrective_hint": "The correct answer should be D.",
        }
    ],
    "quiz_summary": {
        "difficulty_ok": True,
        "duplicate_concepts": [],
        "coverage_issues": [],
    },
    "wrong_answer_risk": "low",
    "corrective_instructions": "Review question 7.",
    "retry_recommendation": {
        "mode": "question_patch",
        "failed_question_ids": [FAILED_QUESTION_ID],
        "missing_concepts": [],
        "rationale": "One question has an incorrect answer.",
    },
}

PATCH_RESPONSE_JSON = """[
  {"question_text": "What is Uvicorn?", "option_a": "A web framework", "option_b": "A database management system", "option_c": "A lightning-fast ASGI server", "option_d": "A load balancer", "correct_option": "C", "explanation": "Uvicorn is a lightning-fast ASGI server.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Introduction to Uvicorn"},
  {"question_text": "How do you install Uvicorn?", "option_a": "Using a package manager like pip", "option_b": "Compiling from source", "option_c": "Using a Docker container", "option_d": "Downloading a pre-compiled binary", "correct_option": "A", "explanation": "Install with pip.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Installing and Running Uvicorn"},
  {"question_text": "What is the purpose of the workers parameter in Uvicorn?", "option_a": "To specify the host and port to bind to", "option_b": "To specify the number of worker processes to use", "option_c": "To specify the log level", "option_d": "To specify the debug mode", "correct_option": "B", "explanation": "Workers controls process count.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Configuring Uvicorn"},
  {"question_text": "How do you run a FastAPI application using Uvicorn?", "option_a": "Using the uvicorn.run function with the app instance", "option_b": "Using the uvicorn.run function with the app module", "option_c": "Using the fastapi.run function", "option_d": "Using the python -m uvicorn command", "correct_option": "A", "explanation": "Pass app instance to uvicorn.run.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Uvicorn with Frameworks"},
  {"question_text": "What is the purpose of the debug parameter in Uvicorn?", "option_a": "To enable the built-in debugger", "option_b": "To disable the built-in debugger", "option_c": "To specify the log level", "option_d": "To specify the number of worker processes", "correct_option": "A", "explanation": "debug=True enables debugger.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Debugging and Logging"},
  {"question_text": "How do you configure logging for a Uvicorn application?", "option_a": "Using the logging.basicConfig function", "option_b": "Using the uvicorn.logging.configure function", "option_c": "Using the fastapi.logging.configure function", "option_d": "Using the python -m logging command", "correct_option": "A", "explanation": "Use logging.basicConfig.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Debugging and Logging"},
  {"question_text": "What is the benefit of using Uvicorn with a framework like FastAPI?", "option_a": "Improved security features", "option_b": "Simplified development and deployment", "option_c": "Enhanced performance and scalability", "option_d": "All of the above", "correct_option": "D", "explanation": "Performance, deployment, and security benefits.", "difficulty": "hard", "domain": "Programming", "topic_tag": "Uvicorn with Frameworks"},
  {"question_text": "How do you handle errors in a Uvicorn application?", "option_a": "Using try-except blocks", "option_b": "Using the logging.error function", "option_c": "Using the uvicorn.error_handler function", "option_d": "Using the fastapi.error_handler function", "correct_option": "B", "explanation": "Log errors with logging.error.", "difficulty": "hard", "domain": "Programming", "topic_tag": "Debugging and Logging"},
  {"question_text": "What is the purpose of the host and port parameters in Uvicorn?", "option_a": "To specify the number of worker processes to use", "option_b": "To specify the log level", "option_c": "To specify the host and port to bind to", "option_d": "To specify the debug mode", "correct_option": "C", "explanation": "host/port set bind target.", "difficulty": "easy", "domain": "Programming", "topic_tag": "Configuring Uvicorn"},
  {"question_text": "How do you run a Uvicorn application in production mode?", "option_a": "Using uvicorn.run with debug=True", "option_b": "Using uvicorn.run with workers=1", "option_c": "Using uvicorn.run with log_level=info", "option_d": "Using uvicorn.run with host 0.0.0.0 and port 8000", "correct_option": "D", "explanation": "Production bind settings.", "difficulty": "medium", "domain": "Programming", "topic_tag": "Configuring Uvicorn"}
]"""


def _build_initial_questions() -> list[dict]:
    items = parse_json_array(INITIAL_GENERATION_JSON)
    parsed, _ = normalize_parsed_items(items)
    stable_ids = [
        "540380e3-13bf-42dd-803e-2cd67c706a16",
        "abfad59b-c06b-4629-b7c3-5e57636ceeba",
        "e421513f-318b-4b3b-8a88-310010308a5a",
        "0a73c11a-259d-43ed-828e-a0a3ee5db633",
        "9ae4bee9-04cb-46e9-b4b8-4a18e5742863",
        "90d4e9b1-01e0-4601-8b49-a60a3f2246b3",
        FAILED_QUESTION_ID,
        "72566a2e-c26a-4dcd-b319-c2353f7f97f9",
        "87d124c4-53d1-42f9-9110-eb3a780fe674",
        "dfa30646-047a-4c20-93f6-0c14f008e471",
    ]
    for question, question_id in zip(parsed, stable_ids, strict=True):
        question["question_id"] = question_id
    return parsed


def _build_qc_result_from_verification(questions: list[dict]) -> dict:
    """Minimal qc_result shape after build_final_quiz_qc_result for routing tests."""
    failed_check = {
        "id": "answer_correctness_7",
        "category": "answer_correctness",
        "question_id": FAILED_QUESTION_ID,
        "passed": False,
        "severity": "critical",
        "evidence": "Marked option A does not match independent answer D.",
        "corrective_hint": "The correct answer should be D.",
    }
    passing_checks = [
        {
            "id": f"answer_correctness_{index}",
            "category": "answer_correctness",
            "question_id": str(question.get("question_id")),
            "passed": True,
            "severity": "critical",
            "evidence": "ok",
            "corrective_hint": "",
        }
        for index, question in enumerate(questions, start=1)
        if str(question.get("question_id")) != FAILED_QUESTION_ID
    ]
    checks = passing_checks + [failed_check]
    return {
        "checks": checks,
        "failed_checks": [failed_check],
        "overall_status": "fail",
        "wrong_answer_risk": "low",
        "retry_recommendation": QC_VERIFICATION_JSON["retry_recommendation"],
    }


def _llm_result(*, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        content=content,
        error_type=None,
        provider_meta=None,
        next_llm_retry_at=None,
        model="llama-3.3-70b-versatile",
        token_usage=100,
    )


class TestOopslogQcPatchRegression:
    """Step-by-step regression for the production Uvicorn quiz failure."""

    def test_qc_routing_stays_question_patch_for_single_failure(self) -> None:
        questions = _build_initial_questions()
        qc_result = _build_qc_result_from_verification(questions)
        routing = classify_quiz_retry_routing(qc_result, questions)
        assert routing.mode == "question_patch", (
            f"Expected question_patch, got {routing.mode!r} — "
            "single failure on 10-question quiz must not escalate to full_regeneration"
        )
        assert routing.failed_question_ids == [FAILED_QUESTION_ID]

    def test_patch_merge_keeps_ten_questions_and_fixes_failed_slot(self) -> None:
        existing = _build_initial_questions()
        patch_items = parse_json_array(PATCH_RESPONSE_JSON)
        patch_parsed, _ = normalize_parsed_items(patch_items)

        merged = prepare_question_patches_for_merge(
            existing,
            patch_parsed,
            target_question_ids=[FAILED_QUESTION_ID],
        )
        assert len(merged) == 10, (
            f"Patch merge produced {len(merged)} questions; expected exactly 10"
        )
        failed = next(
            q for q in merged if str(q.get("question_id")) == FAILED_QUESTION_ID
        )
        assert failed["correct_option"] == "D", (
            "Failed question slot must be updated to correct_option D"
        )
        unchanged = next(
            q
            for q in merged
            if str(q.get("question_id")) == "540380e3-13bf-42dd-803e-2cd67c706a16"
        )
        assert "primary purpose" in unchanged["question_text"].lower(), (
            "Non-failed questions must be preserved during targeted patch"
        )

    def test_full_regen_merge_does_not_accumulate_to_twenty(self) -> None:
        previous = _build_initial_questions()
        regen_items = parse_json_array(PATCH_RESPONSE_JSON)
        regen_parsed, _ = normalize_parsed_items(regen_items)

        merged = merge_full_regeneration_preserving_passing(
            regen_parsed,
            previous,
            rewrite_question_ids={FAILED_QUESTION_ID},
        )
        assert len(merged) == 10, (
            f"Full-regen merge accumulated {len(merged)} questions; expected 10"
        )

    def test_deterministic_validate_passes_after_patch(self) -> None:
        existing = _build_initial_questions()
        patch_items = parse_json_array(PATCH_RESPONSE_JSON)
        patch_parsed, _ = normalize_parsed_items(patch_items)
        merged = prepare_question_patches_for_merge(
            existing,
            patch_parsed,
            target_question_ids=[FAILED_QUESTION_ID],
        )
        checks = run_deterministic_quiz_checks(merged, expected_count=10)
        failed = [check for check in checks if not check.get("passed", True)]
        assert not failed, (
            "Deterministic validation must pass after patch; failures: "
            + ", ".join(check.get("id", "?") for check in failed)
        )

    def test_routing_after_qc_fail_goes_to_generator_not_loop(self) -> None:
        state = {
            "qc_passed": False,
            "qc_failed_permanently": False,
            "qc_retry_mode": "question_patch",
            "qc_result": {},
            "qc_attempt": 1,
        }
        assert _route_after_quality_check(state) == "quiz_generator"

    def test_routing_after_patch_does_not_reenter_generator_loop(self) -> None:
        state = {
            "parsed_questions": _build_initial_questions(),
            "struct_validation_passed": True,
            "qc_retry_mode": "question_patch",
        }
        assert _route_after_quiz_generator(state) == "deterministic_validate"
        assert _route_after_deterministic_validate(state) == "quality_check"


class TestOopslogGraphRegression:
    """Graph-level regression with mocked LLM: generate → QC fail → patch → persist."""

    def test_graph_completes_without_question_accumulation(self) -> None:
        async def _run() -> dict:
            node_id = uuid4()
            mentor_id = uuid4()
            space_id = uuid4()
            quiz_id = uuid4()

            patch_items = parse_json_array(PATCH_RESPONSE_JSON)
            patch_parsed, _ = normalize_parsed_items(patch_items)

            call_count = {"n": 0}

            async def _mock_quiz_llm(*, system_prompt: str, user_message: str):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return _llm_result(content=INITIAL_GENERATION_JSON)
                return _llm_result(content=PATCH_RESPONSE_JSON)

            qc_pass = {"done": False}

            async def _mock_verification(**kwargs):
                if not qc_pass["done"]:
                    verification = {
                        "question_results": [
                            {
                                "question_id": FAILED_QUESTION_ID,
                                "question_number": 7,
                                "answer_correctness_passed": False,
                                "quality_passed": True,
                                "corrective_hint": "Fix answer to D.",
                            }
                        ],
                        "wrong_answer_risk": "low",
                        "retry_recommendation": {
                            "mode": "question_patch",
                            "failed_question_ids": [FAILED_QUESTION_ID],
                        },
                    }
                    meta = {
                        "llm_ok": True,
                        "parse_ok": True,
                        "llm_model_used": "qc-model",
                    }
                    return verification, meta

                verification = {
                    "question_results": [
                        {
                            "question_id": FAILED_QUESTION_ID,
                            "question_number": 7,
                            "answer_correctness_passed": True,
                            "quality_passed": True,
                            "corrective_hint": "",
                        }
                    ],
                    "wrong_answer_risk": "low",
                    "retry_recommendation": {"mode": "none"},
                }
                meta = {"llm_ok": True, "parse_ok": True, "llm_model_used": "qc-model"}
                return verification, meta

            mock_node = MagicMock()
            mock_node.space_id = space_id
            mock_node.title = "Uvicorn"

            active_version = SimpleNamespace(
                version_id=uuid4(),
                content="Uvicorn study material content.",
                concept_plan=None,
            )
            mock_study_repo = MagicMock()
            mock_study_repo.get_published_version = AsyncMock(return_value=None)
            mock_study_repo.get_active_version = AsyncMock(return_value=active_version)
            mock_study_repo.get_latest_workspace_draft = AsyncMock(return_value=None)

            mock_repo = MagicMock()
            mock_repo.create_quiz_draft_with_questions = AsyncMock(return_value=quiz_id)

            initial_state = {
                "node_id": node_id,
                "space_id": space_id,
                "mentor_id": mentor_id,
                "mode": "generate",
                "question_count": 10,
                "difficulty": "mixed",
            }
            config = {"configurable": {"session": MagicMock()}}

            reset_quiz_generation_graph()
            graph = build_quiz_generation_graph()
            visited: list[str] = []

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
                    "src.api.control.quiz_agent.nodes.quiz_graph.persist_quiz_draft_node.QuizRepository",
                    return_value=mock_repo,
                ),
                patch(
                    "src.api.utils.quiz_utils.graph.node_helpers.call_quiz_llm",
                    side_effect=_mock_quiz_llm,
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.quality_check_node.run_quiz_verification_pass",
                    side_effect=_mock_verification,
                ),
            ):
                final_state: dict = {}
                async for chunk in graph.astream(
                    initial_state,
                    config,
                    stream_mode="updates",
                ):
                    visited.extend(chunk.keys())
                    for update in chunk.values():
                        if isinstance(update, dict):
                            final_state.update(update)
                            if update.get("qc_passed"):
                                qc_pass["done"] = True

            return {
                "visited": visited,
                "generator_hits": visited.count("quiz_generator"),
                "final_state": final_state,
                "persist_questions": mock_repo.create_quiz_draft_with_questions.await_args,
            }

        result = asyncio.run(_run())
        visited = result["visited"]
        final_state = result["final_state"]

        assert "persist_quiz_draft" in visited, (
            f"Graph never reached persist_quiz_draft; visited={visited}"
        )
        assert result["generator_hits"] <= 2, (
            f"quiz_generator ran {result['generator_hits']} times; "
            "expected at most 2 (initial + patch), not a det-validate loop"
        )

        persisted = result["persist_questions"]
        assert persisted is not None, "Quiz was not persisted"
        questions_arg = persisted.kwargs.get("questions") or persisted.args[4]
        assert len(questions_arg) == 10, (
            f"Persisted {len(questions_arg)} questions; demo requires exactly 10"
        )

        validated = final_state.get("validated_questions") or []
        if validated:
            assert len(validated) == 10


class TestExecuteGenerateQuizMarksRunFailed:
    """Malformed quiz_generator output must not leave generationruns stuck running."""

    def test_parse_failure_marks_run_failed(self) -> None:
        async def _run() -> None:
            from src.api.core.exceptions import QuizGenerationFailedException
            from src.api.core.services.quiz_services.quiz_service import QuizService
            from src.api.schemas.common import GenerationRunStatus

            run_id = uuid4()
            node_id = uuid4()
            mentor_id = uuid4()
            session = MagicMock()

            run = MagicMock()
            run.run_id = run_id
            run.status = GenerationRunStatus.RUNNING.value
            run.request_params = {
                "node_id": str(node_id),
                "mode": "generate",
                "question_count": 10,
                "difficulty": "mixed",
            }

            run_service = MagicMock()
            run_service.acquire_lock_for_run = AsyncMock(return_value=run)
            run_service.fail_run = AsyncMock()

            service = QuizService(session)
            service._fail_generation_run = AsyncMock()  # noqa: SLF001

            with (
                patch(
                    "src.api.core.services.quiz_services.quiz_service.GenerationRunService",
                    return_value=run_service,
                ),
                patch(
                    "src.api.control.quiz_agent.graph.quiz_graph.runner.run_quiz_generation",
                    AsyncMock(
                        side_effect=QuizGenerationFailedException(
                            "Malformed quiz output: Expecting value"
                        )
                    ),
                ),
            ):
                await service.execute_generate_quiz(
                    run_id=run_id,
                    user_id=mentor_id,
                )

            service._fail_generation_run.assert_awaited_once()
            await_args = service._fail_generation_run.await_args
            assert await_args.args[0] == run_id
            assert "Malformed quiz output" in str(await_args.kwargs.get("exc"))

        asyncio.run(_run())
