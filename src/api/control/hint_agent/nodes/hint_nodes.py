"""Node functions for the hint generation LangGraph (Graph 2).

Every node is a plain async function that receives the running
``HintGraphState`` and returns a partial state update. DB access goes only
through the existing repository layer; prompt assembly goes only through the
existing prompt builder. The ``AsyncSession`` is threaded in via the graph
invocation config — nodes never create their own session.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config.llm_config import llm_settings
from src.api.control.hint_agent.prompts.hint_prompt import build_hint_prompt
from src.api.control.hint_agent.states.hint_state import HintGraphState
from src.api.core.exceptions.quiz_exceptions.hint_generation_exceptions import (
    HintsCannotGenerateOnPublishedQuizException,
    QuizHasNoQuestionsException,
)
from src.api.core.exceptions.quiz_exceptions.trainee_quiz_exceptions import (
    QuizNotFoundException,
)
from src.api.data.repositories.quiz_repositories.hint_repository import HintRepository
from src.api.schemas.common.generation_diagnostics_schema import (
    HintGenerationDiagnosticsOut,
    HintQuestionErrorOut,
)
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation
from src.api.utils.LLM_utils.llm_failure_diagnostics import (
    build_hint_invoke_failure_diagnostics,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _get_node_and_assert_space_access,
)

logger = logging.getLogger(__name__)

_BANNED_PHRASES = ("the correct answer is", "the answer is")


# ── Shared helpers ────────────────────────────────────────────────────────


def _session(config: RunnableConfig) -> AsyncSession:
    """Pull the AsyncSession passed into the graph invocation config."""
    return cast(AsyncSession, config["configurable"]["session"])


def _parse_json_array(raw: str) -> list:
    """Parse an LLM response that should be a JSON array.

    Tolerates accidental ```json fences around the payload.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    return parsed


# ── Nodes ─────────────────────────────────────────────────────────────────


async def load_hint_context(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    session = _session(config)

    # Verify the mentor owns the node's space (raises on failure).
    node = await _get_node_and_assert_space_access(
        session, state["node_id"], state["mentor_id"], owner_only=True
    )

    repo = HintRepository(session)
    quiz = await repo.get_quiz_by_id(state["quiz_id"])
    if quiz is None or quiz.node_id != state["node_id"]:
        raise QuizNotFoundException()
    if quiz.is_published:
        raise HintsCannotGenerateOnPublishedQuizException()

    questions = await repo.get_active_questions_by_quiz(state["quiz_id"])
    if not questions:
        raise QuizHasNoQuestionsException()

    questions_for_hinting = [
        {
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "explanation": q.explanation,
        }
        for q in questions
    ]

    # Apply filter if specific question IDs were requested (for selective regeneration)
    filter_ids = state.get("questions_filter_ids")
    if filter_ids:
        filter_set = {str(fid) for fid in filter_ids}
        questions_for_hinting = [
            q for q in questions_for_hinting if q["question_id"] in filter_set
        ]
        if not questions_for_hinting:
            raise QuizHasNoQuestionsException()

    return {
        **state,
        "space_id": cast(UUID, node.space_id),
        "questions_for_hinting": questions_for_hinting,
    }


async def build_hint_prompt_payload(state: HintGraphState) -> HintGraphState:
    is_regeneration = bool(state.get("questions_filter_ids"))
    prompt_input = build_hint_prompt(
        questions_for_hinting=state.get("questions_for_hinting") or [],
        topic_title=None,
        is_regeneration=is_regeneration,
        mentor_feedback=state.get("mentor_feedback"),
    )
    return {**state, "prompt_input": prompt_input}


async def invoke_hint_llm(state: HintGraphState) -> HintGraphState:
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {**state, "error": "Missing prompt input for hint generation."}

    result = await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_input["system_prompt"]),
            HumanMessage(content=prompt_input["user_message"]),
        ],
        model=llm_settings.llm_model,
        temperature=0.4,
        timeout=120,
        graph_node="hint_generator",
    )
    if not result.ok:
        logger.error(
            "Groq hint generation failed: %s",
            result.error_type,
        )
        return {
            **state,
            "terminal_llm_failure": True,
            "hint_generation_diagnostics": build_hint_invoke_failure_diagnostics(
                result
            ),
            "next_llm_retry_at": result.next_llm_retry_at,
        }

    return {
        **state,
        "raw_llm_output": result.content or "",
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
    }


async def parse_hint_output(state: HintGraphState) -> HintGraphState:
    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = _parse_json_array(raw)
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed hint output: {exc}"}

    questions = state.get("questions_for_hinting") or []
    valid_ids = {q["question_id"] for q in questions}

    parsed: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            return {**state, "error": "Hint output element is not an object."}

        question_id = item.get("question_id")
        if question_id is None:
            return {**state, "error": "Hint output element missing question_id."}
        question_id = str(question_id)
        if question_id not in valid_ids:
            return {
                **state,
                "error": f"Hint references unknown question_id: {question_id}.",
            }

        for field in ("hint_1", "hint_2", "hint_3"):
            if field not in item:
                return {**state, "error": f"Hint output missing field: {field}."}

        parsed.append(
            {
                "question_id": question_id,
                "hint_1": item.get("hint_1"),
                "hint_2": item.get("hint_2"),
                "hint_3": item.get("hint_3"),
            }
        )

    return {**state, "parsed_hints": parsed}


def _hint_quality_issue(hint_1: Any, hint_2: Any, hint_3: Any) -> str | None:
    """Return an error type when hints fail validation, else None."""
    for value in (hint_1, hint_2, hint_3):
        if not isinstance(value, str) or not value.strip():
            return "hint_quality_error"
        lowered = value.lower()
        if any(phrase in lowered for phrase in _BANNED_PHRASES):
            return "hint_quality_error"
    h1 = str(hint_1).strip()
    h3 = str(hint_3).strip()
    if len(h1) > len(h3):
        return "hint_quality_error"
    return None


async def _regenerate_hints_for_question(
    question: dict[str, Any],
    state: HintGraphState,
) -> dict[str, Any] | None:
    """Call the LLM for a single question and return parsed hints or None."""
    is_regeneration = bool(state.get("questions_filter_ids"))
    prompt_input = build_hint_prompt(
        questions_for_hinting=[question],
        topic_title=None,
        is_regeneration=is_regeneration,
        mentor_feedback=state.get("mentor_feedback"),
    )
    result = await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_input["system_prompt"]),
            HumanMessage(content=prompt_input["user_message"]),
        ],
        model=llm_settings.llm_model,
        temperature=0.4,
        timeout=120,
        graph_node="hint_generator",
    )
    if not result.ok:
        return None

    try:
        items = _parse_json_array(result.content or "")
    except Exception:  # noqa: BLE001
        return None

    question_id = question["question_id"]
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("question_id")) != question_id:
            continue
        for field in ("hint_1", "hint_2", "hint_3"):
            if field not in item:
                return None
        return {
            "question_id": question_id,
            "hint_1": item.get("hint_1"),
            "hint_2": item.get("hint_2"),
            "hint_3": item.get("hint_3"),
        }
    return None


async def validate_hint_quality(state: HintGraphState) -> HintGraphState:
    questions = state.get("questions_for_hinting") or []
    parsed = state.get("parsed_hints") or []

    by_question_id: dict[str, dict] = {}
    for hint in parsed:
        question_id = hint["question_id"]
        if question_id in by_question_id:
            return {
                **state,
                "error": "Hint validation failed: duplicate question_id in LLM output.",
            }
        by_question_id[question_id] = hint

    validated: list[dict] = []
    question_errors: list[dict[str, Any]] = []

    for q in questions:
        qid = q["question_id"]
        hint = by_question_id.get(qid)
        attempts = 0
        max_retries = llm_settings.hint_quality_max_retries

        while attempts <= max_retries:
            if hint is not None:
                issue = _hint_quality_issue(
                    hint.get("hint_1"), hint.get("hint_2"), hint.get("hint_3")
                )
                if issue is None:
                    validated.append(
                        {
                            "question_id": qid,
                            "hint_1": hint["hint_1"],
                            "hint_2": hint["hint_2"],
                            "hint_3": hint["hint_3"],
                        }
                    )
                    break

            if attempts >= max_retries:
                question_errors.append(
                    HintQuestionErrorOut(
                        question_id=UUID(qid),
                        error_type="hint_quality_error",
                        attempts=attempts + 1,
                    ).model_dump(by_alias=True)
                )
                break

            attempts += 1
            hint = await _regenerate_hints_for_question(q, state)

    diagnostics: dict[str, Any] | None = None
    if question_errors:
        diagnostics = HintGenerationDiagnosticsOut.model_validate(
            {"questionErrors": question_errors}
        ).model_dump(by_alias=True, exclude_none=True)

    return {
        **state,
        "validated_hints": validated,
        "hint_generation_diagnostics": diagnostics,
    }


async def persist_hints_to_questions(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    session = _session(config)
    repo = HintRepository(session)
    validated = state.get("validated_hints") or []

    for hint in validated:
        await repo.update_question_hints(
            UUID(hint["question_id"]),
            hint["hint_1"],
            hint["hint_2"],
            hint["hint_3"],
            commit=False,
        )

    diagnostics = state.get("hint_generation_diagnostics")
    next_llm_retry_at = state.get("next_llm_retry_at")
    if diagnostics:
        await repo.merge_quiz_qc_result(
            state["quiz_id"],
            {"hintGeneration": diagnostics},
            next_llm_retry_at=next_llm_retry_at,
        )
    elif validated:
        await repo.touch_quiz_updated_at(state["quiz_id"])
    else:
        await session.commit()

    return state


async def persist_hint_failure_diagnostics(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    """Persist hint LLM failure diagnostics without modifying existing hints."""
    session = _session(config)
    repo = HintRepository(session)
    diagnostics = state.get("hint_generation_diagnostics")
    if diagnostics:
        await repo.merge_quiz_qc_result(
            state["quiz_id"],
            {"hintGeneration": diagnostics},
            next_llm_retry_at=state.get("next_llm_retry_at"),
        )
    return state
