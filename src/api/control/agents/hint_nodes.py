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
from typing import cast
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config.dbconfig import settings
from src.api.control.agents.quiz_state import HintGraphState
from src.api.control.prompts.quiz_prompts.hint_prompt import build_hint_prompt
from src.api.core.exceptions.quiz_exceptions.hint_generation_exceptions import (
    HintsCannotGenerateOnPublishedQuizException,
    QuizHasNoQuestionsException,
)
from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizNotFoundException,
)
from src.api.data.repositories.quiz_repositories.hint_repository import HintRepository
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.groq_retry import invoke_llm_rotating

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

    version = await repo.get_study_material_version(
        cast(UUID, quiz.study_material_version_id)
    )
    study_material_content = cast(str, version.content) if version is not None else None

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
        "study_material_version_id": cast(UUID, quiz.study_material_version_id),
        "study_material_content": study_material_content,
        "questions_for_hinting": questions_for_hinting,
    }


async def build_hint_prompt_payload(state: HintGraphState) -> HintGraphState:
    is_regeneration = bool(state.get("questions_filter_ids"))
    prompt_input = build_hint_prompt(
        study_material_content=state.get("study_material_content"),
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

    try:
        raw, model, token_usage = await invoke_llm_rotating(
            messages=[
                SystemMessage(content=prompt_input["system_prompt"]),
                HumanMessage(content=prompt_input["user_message"]),
            ],
            model=settings.llm_model,
            temperature=0.4,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Hint LLM invocation failed after retries")
        return {**state, "error": f"Hint generation failed: {exc}"}

    return {
        **state,
        "raw_llm_output": raw,
        "llm_model_used": model,
        "token_usage": token_usage,
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


async def validate_hint_quality(state: HintGraphState) -> HintGraphState:
    questions = state.get("questions_for_hinting") or []
    parsed = state.get("parsed_hints") or []

    by_question_id: dict[str, dict] = {}
    for hint in parsed:
        question_id = hint["question_id"]
        # Exactly one hint set per question — duplicates are a failure.
        if question_id in by_question_id:
            return {
                **state,
                "error": "Hint validation failed: duplicate question_id in LLM output.",
            }
        by_question_id[question_id] = hint

    question_ids = {q["question_id"] for q in questions}
    if set(by_question_id.keys()) != question_ids:
        missing = question_ids - set(by_question_id.keys())
        extra = set(by_question_id.keys()) - question_ids
        parts: list[str] = []
        if missing:
            parts.append(f"missing hints for {len(missing)} question(s)")
        if extra:
            parts.append(f"unexpected question_id(s): {', '.join(sorted(extra))}")
        return {
            **state,
            "error": f"Hint validation failed: {'; '.join(parts)}.",
        }

    validated: list[dict] = []
    for q in questions:
        hint = by_question_id[q["question_id"]]
        hint_1 = hint.get("hint_1")
        hint_2 = hint.get("hint_2")
        hint_3 = hint.get("hint_3")

        for value in (hint_1, hint_2, hint_3):
            if not isinstance(value, str) or not value.strip():
                return {
                    **state,
                    "error": "Hint validation failed: a hint field is missing or empty.",  # noqa: E501
                }
            lowered = value.lower()
            if any(phrase in lowered for phrase in _BANNED_PHRASES):
                return {
                    **state,
                    "error": "Hint validation failed: a hint reveals the answer.",
                }

        validated.append(
            {
                "question_id": q["question_id"],
                "hint_1": hint_1,
                "hint_2": hint_2,
                "hint_3": hint_3,
            }
        )

    return {**state, "validated_hints": validated}


async def persist_hints_to_questions(
    state: HintGraphState, config: RunnableConfig
) -> HintGraphState:
    session = _session(config)
    repo = HintRepository(session)
    validated = state.get("validated_hints") or []

    updates = [
        (UUID(h["question_id"]), h["hint_1"], h["hint_2"], h["hint_3"])
        for h in validated
    ]
    await repo.bulk_update_question_hints(updates)
    await repo.touch_quiz_updated_at(state["quiz_id"])

    return state
