"""Node functions for the quiz single-question regeneration LangGraph."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node import (
    load_generation_context,
)
from src.api.control.quiz_agent.prompts.quiz_single_regen_graph.quiz_single_regen_prompt import (
    build_quiz_single_regen_prompt,
)
from src.api.control.quiz_agent.states.quiz_single_regen_graph.quiz_single_regen_state import (
    QuizSingleRegenGraphState,
)
from src.api.core.exceptions import (
    QuizAlreadyPublishedException,
    QuizNotFoundException,
    QuizQuestionNotFoundException,
)
from src.api.data.repositories import QuizRepository
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)
from src.api.utils.quiz_utils.graph.node_helpers import (
    call_quiz_llm,
    format_gen_feedback_from_checks,
    graph_session,
    log_quiz_artifact,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)

logger = logging.getLogger(__name__)


def _question_to_dict(question: Any) -> dict[str, Any]:
    return {
        "question_id": str(question.question_id),
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_option": question.correct_option,
        "explanation": question.explanation,
        "order_index": question.order_index,
    }


def _restore_patch_order_indices(
    patches: list[dict[str, Any]],
    all_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    order_by_id = {
        str(question.get("question_id", "")).strip(): question.get("order_index")
        for question in all_questions
        if str(question.get("question_id", "")).strip()
    }
    restored: list[dict[str, Any]] = []
    for patch in patches:
        updated = dict(patch)
        question_id = str(updated.get("question_id", "")).strip()
        if question_id in order_by_id:
            updated["order_index"] = order_by_id[question_id]
        restored.append(updated)
    return restored


async def load_quiz_single_regen_context(
    state: QuizSingleRegenGraphState, config: RunnableConfig
) -> QuizSingleRegenGraphState:
    context_update = await load_generation_context(
        cast(Any, state),
        config,
    )
    merged_state: QuizSingleRegenGraphState = cast(
        QuizSingleRegenGraphState, {**state, **context_update}
    )

    session = graph_session(config)
    repo = QuizRepository(session)
    quiz = await repo.get_quiz_by_id(merged_state["quiz_id"])
    if quiz is None or quiz.node_id != merged_state["node_id"]:
        raise QuizNotFoundException()
    if quiz.is_published:
        raise QuizAlreadyPublishedException()

    active_questions = await repo.get_active_questions_by_quiz(merged_state["quiz_id"])
    active_by_id = {
        str(question.question_id): question for question in active_questions
    }
    target_ids = [str(question_id) for question_id in merged_state["question_ids"]]
    missing = [
        question_id for question_id in target_ids if question_id not in active_by_id
    ]
    if missing:
        raise QuizQuestionNotFoundException()

    all_questions = [_question_to_dict(question) for question in active_questions]
    return {
        **merged_state,
        "all_questions": all_questions,
        "difficulty_profile": cast(str, quiz.difficulty) or "medium",
    }


async def build_quiz_single_regen_prompt_node(
    state: QuizSingleRegenGraphState,
) -> QuizSingleRegenGraphState:
    question_ids = [str(question_id) for question_id in state["question_ids"]]
    prompt_input = build_quiz_single_regen_prompt(
        topic_title=state.get("node_title") or str(state["node_id"]),
        study_material_content=state.get("study_material_content") or "",
        difficulty_profile=state.get("difficulty_profile") or "medium",
        mentor_feedback=state["mentor_feedback"],
        question_ids=question_ids,
        questions=state.get("all_questions") or [],
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
    )
    return {**state, "prompt_input": prompt_input}


async def invoke_quiz_single_regen_llm(
    state: QuizSingleRegenGraphState,
) -> dict[str, Any]:
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {
            **state,
            "error": "Missing prompt input for quiz single-question regen.",
        }

    result = await call_quiz_llm(
        system_prompt=prompt_input["system_prompt"],
        user_message=prompt_input["user_message"],
    )
    if not result.ok:
        logger.error("Groq quiz single-question regen failed: %s", result.error_type)
        failure = {
            **state,
            "terminal_llm_failure": True,
            "llm_error_type": result.error_type,
            "provider_meta": result.provider_meta,
            "next_llm_retry_at": result.next_llm_retry_at,
            "raw_llm_output": result.content,
            "llm_model_used": result.model or llm_settings.llm_model,
            "token_usage": result.token_usage,
        }
        log_quiz_artifact(
            cast(Any, state),
            "quiz_single_regen_llm",
            {
                "prompt_input": prompt_input,
                "raw_llm_output": result.content,
                "terminal_llm_failure": True,
            },
        )
        return failure

    llm_return = {
        **state,
        "raw_llm_output": result.content or "",
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
        "terminal_llm_failure": False,
    }
    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_llm",
        {
            "prompt_input": prompt_input,
            "raw_llm_output": result.content,
            "llm_model_used": llm_return.get("llm_model_used"),
            "token_usage": llm_return.get("token_usage"),
        },
    )
    return llm_return


def _parse_vague_regen_response(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("rework_status") == "vague":
        return parsed
    return None


async def parse_quiz_single_regen_output(
    state: QuizSingleRegenGraphState,
) -> QuizSingleRegenGraphState:
    if state.get("parsed_patches") is not None:
        return state

    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    vague = _parse_vague_regen_response(raw)
    if vague is not None:
        message = str(
            vague.get("message")
            or "Feedback too vague to apply. Specify what to change."
        )
        return {
            **state,
            "rework_status": "vague",
            "error": message,
        }

    expected_ids = {str(question_id) for question_id in state.get("question_ids") or []}
    try:
        items = parse_json_array(raw)
        parsed, hints_stale_ids = normalize_parsed_items(items, cast(Any, state))
        parsed = _restore_patch_order_indices(
            parsed,
            state.get("all_questions") or [],
        )
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed quiz single-question regen output: {exc}"}

    returned_ids = {str(patch.get("question_id", "")).strip() for patch in parsed}
    if returned_ids != expected_ids:
        return {
            **state,
            "error": (
                "Quiz single-question regen output must return exactly the requested question_ids."
            ),
        }

    if not hints_stale_ids:
        hints_stale_ids = list(expected_ids)

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_parse",
        {
            "parsed_patches": parsed,
            "hints_stale_question_ids": hints_stale_ids,
        },
    )
    return {
        **state,
        "parsed_patches": parsed,
        "hints_stale_question_ids": hints_stale_ids,
    }


async def deterministic_validate_question_patches(
    state: QuizSingleRegenGraphState,
) -> dict[str, Any]:
    parsed = state.get("parsed_patches") or []
    expected_count = len(state.get("question_ids") or [])
    det_checks = run_deterministic_quiz_checks(
        parsed,
        expected_count=expected_count,
    )
    failed = [check for check in det_checks if not check.get("passed", True)]

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_deterministic",
        {
            "det_checks": det_checks,
            "parsed_patches": parsed,
        },
    )

    if not failed:
        return {
            "validated_patches": parsed,
            "struct_validation_passed": True,
        }

    feedback = format_gen_feedback_from_checks(failed)
    return {
        "validated_patches": [],
        "struct_validation_passed": False,
        "error": feedback,
    }


async def persist_question_patches(
    state: QuizSingleRegenGraphState, config: RunnableConfig
) -> QuizSingleRegenGraphState:
    session = graph_session(config)
    repo = QuizRepository(session)
    patches = state.get("validated_patches") or []
    if not patches:
        return {**state, "error": "No validated question patches to persist."}

    patched_ids = await repo.patch_questions_from_ai(
        state["quiz_id"],
        patches,
        commit=False,
    )
    if not patched_ids:
        return {**state, "error": "Failed to persist any question patches."}

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_result",
        {
            "quiz_id": str(state["quiz_id"]),
            "patched_question_ids": patched_ids,
            "hints_stale_question_ids": state.get("hints_stale_question_ids"),
        },
    )
    return {
        **state,
        "hints_stale_question_ids": patched_ids,
    }
