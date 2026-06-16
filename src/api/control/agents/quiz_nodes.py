"""Node functions for the quiz draft generation LangGraph (Graph 1).

Every node is a plain async function that receives the running
``QuizGraphState`` and returns a partial state update. DB access goes only
through the existing repository layer; prompt assembly goes only through the
existing prompt builder. The ``AsyncSession`` is threaded in via the graph
invocation config — nodes never create their own session.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config.dbconfig import settings
from src.api.control.agents.quiz_state import QuizGraphState
from src.api.control.prompts.quiz_prompts.quiz_prompt import build_quiz_prompt
from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizHasNoPublishedStudyMaterialException,
    QuizNotFoundException,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (  # noqa: E501
    StudyMaterialRepository,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.groq_retry import invoke_llm_rotating

logger = logging.getLogger(__name__)

_VALID_CORRECT_OPTIONS = {"A", "B", "C", "D"}


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


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


async def _format_markdown_code_blocks(text: str) -> str:
    """Format code blocks in text using a fast LLM call if present."""
    if not isinstance(text, str) or "```" not in text:
        return text

    prompt = (
        "You are an expert code formatter. "
        "The following text contains markdown code blocks (```...```) that have been flattened onto a single line. "  # noqa: E501
        "Your task is to reconstruct the proper indentation and newlines for the code inside the blocks. "  # noqa: E501
        "DO NOT change any text outside the code blocks. "
        "Output ONLY the fully formatted text and nothing else. No preamble, no explanation."  # noqa: E501
    )

    try:
        content, _, _ = await invoke_llm_rotating(
            messages=[
                SystemMessage(content=prompt),
                HumanMessage(content=text),
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
            timeout=30,
        )
        return content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to format code blocks: %s", exc)
        return text


# ── Nodes ─────────────────────────────────────────────────────────────────


async def load_generation_context(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = _session(config)

    # Verify node exists/active and mentor owns its space (raises on failure).
    node = await _get_node_and_assert_space_access(
        session, state["node_id"], state["mentor_id"], owner_only=True
    )

    study_repo = StudyMaterialRepository(session)
    version = await study_repo.get_published_version(state["node_id"])
    if version is None:
        raise QuizHasNoPublishedStudyMaterialException()

    from uuid import UUID  # noqa: PLC0415

    return {
        **state,
        "space_id": cast(UUID, node.space_id),
        "node_title": cast(str, node.title),
        "study_material_version_id": cast(UUID, version.version_id),
        "study_material_content": cast(str, version.content),
    }


async def load_existing_quiz_if_regenerate(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    if state.get("mode") != "regenerate":
        return state

    session = _session(config)
    repo = QuizRepository(session)

    quiz_id = state.get("quiz_id")
    quiz = await repo.get_quiz_by_id(quiz_id) if quiz_id is not None else None
    if quiz is None or quiz.node_id != state["node_id"]:
        raise QuizNotFoundException()

    questions = await repo.get_active_questions_by_quiz(quiz_id)  # type: ignore[arg-type]
    existing = [
        {
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "explanation": q.explanation,
            "order_index": q.order_index,
        }
        for q in questions
    ]

    return {**state, "existing_quiz_questions": existing}


async def build_quiz_prompt_payload(state: QuizGraphState) -> QuizGraphState:
    prompt_input = build_quiz_prompt(
        node_title=state.get("node_title"),
        study_material_content=state.get("study_material_content"),
        question_count=state["question_count"],
        difficulty=state["difficulty"],
        mode=state.get("mode", "generate"),
        existing_quiz_questions=state.get("existing_quiz_questions"),
        mentor_feedback=state.get("mentor_feedback"),
    )
    return {**state, "prompt_input": prompt_input}


async def invoke_quiz_llm(state: QuizGraphState) -> QuizGraphState:
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {**state, "error": "Missing prompt input for quiz generation."}

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
        logger.exception("Quiz LLM invocation failed after retries")
        return {**state, "error": f"Quiz generation failed: {exc}"}

    return {
        **state,
        "raw_llm_output": raw,
        "llm_model_used": model,
        "token_usage": token_usage,
    }


async def parse_quiz_output(state: QuizGraphState) -> QuizGraphState:
    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = _parse_json_array(raw)
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed quiz output: {exc}"}

    parsed: list[dict] = []
    order_index = 0
    for item in items:
        if not isinstance(item, dict):
            return {**state, "error": "Quiz output element is not an object."}

        question_text = item.get("question_text")
        # Skip the optional shortfall marker described in the prompt contract.
        if isinstance(question_text, str) and question_text.startswith(
            "GENERATION NOTE"
        ):
            continue

        for field in (
            "question_text",
            "option_a",
            "option_b",
            "correct_option",
            "explanation",
        ):
            if item.get(field) in (None, ""):
                return {
                    **state,
                    "error": f"Quiz question missing required field: {field}.",
                }

        question_text = item.get("question_text")
        explanation = item.get("explanation")
        opt_a = item.get("option_a")
        opt_b = item.get("option_b")
        opt_c = _empty_to_none(item.get("option_c"))
        opt_d = _empty_to_none(item.get("option_d"))

        # Format code blocks concurrently
        tasks = [
            _format_markdown_code_blocks(question_text)
            if isinstance(question_text, str)
            else asyncio.sleep(0),  # noqa: E501
            _format_markdown_code_blocks(explanation)
            if isinstance(explanation, str)
            else asyncio.sleep(0),  # noqa: E501
            _format_markdown_code_blocks(opt_a)
            if isinstance(opt_a, str)
            else asyncio.sleep(0),  # noqa: E501
            _format_markdown_code_blocks(opt_b)
            if isinstance(opt_b, str)
            else asyncio.sleep(0),  # noqa: E501
            _format_markdown_code_blocks(opt_c)
            if isinstance(opt_c, str)
            else asyncio.sleep(0),  # noqa: E501
            _format_markdown_code_blocks(opt_d)
            if isinstance(opt_d, str)
            else asyncio.sleep(0),  # noqa: E501
        ]

        formatted_results = await asyncio.gather(*tasks)
        q_text, expl, a, b, c, d = formatted_results

        parsed.append(
            {
                "question_text": q_text or question_text,
                "option_a": a or opt_a,
                "option_b": b or opt_b,
                "option_c": c or opt_c,
                "option_d": d or opt_d,
                "correct_option": item.get("correct_option"),
                "explanation": expl or explanation,
                "order_index": order_index,
            }
        )
        order_index += 1

    quiz_title = f"{state.get('node_title') or 'Quiz'} — Quiz"
    return {**state, "parsed_questions": parsed, "quiz_title": quiz_title}


async def validate_quiz_structure(state: QuizGraphState) -> QuizGraphState:
    parsed = state.get("parsed_questions") or []

    if len(parsed) != state["question_count"]:
        return {
            **state,
            "error": (
                f"LLM returned {len(parsed)} questions but "
                f"{state['question_count']} were requested. Please try again."
            ),
        }

    seen_texts: set[str] = set()
    for q in parsed:
        option_a = q.get("option_a")
        option_b = q.get("option_b")
        option_c = q.get("option_c")
        option_d = q.get("option_d")
        correct_option = q.get("correct_option")
        explanation = q.get("explanation")
        question_text = q.get("question_text")

        # option_a and option_b must be present and non-empty.
        if not (isinstance(option_a, str) and option_a.strip()):
            return {
                **state,
                "error": "Quiz validation failed: option_a is missing or empty.",
            }
        if not (isinstance(option_b, str) and option_b.strip()):
            return {
                **state,
                "error": "Quiz validation failed: option_b is missing or empty.",
            }

        # option_c / option_d may be None but never an empty string.
        for optional in (option_c, option_d):
            if optional is not None and (
                not isinstance(optional, str) or optional.strip() == ""
            ):
                return {
                    **state,
                    "error": "Quiz validation failed: optional answer is blank.",
                }

        # correct_option must be A-D and map to a non-None option.
        if correct_option not in _VALID_CORRECT_OPTIONS:
            return {
                **state,
                "error": f"Quiz validation failed: invalid correct_option {correct_option!r}.",  # noqa: E501
            }
        option_map = {
            "A": option_a,
            "B": option_b,
            "C": option_c,
            "D": option_d,
        }
        if option_map[correct_option] is None:
            return {
                **state,
                "error": "Quiz validation failed: correct_option points to a missing option.",  # noqa: E501
            }

        # No blank explanations.
        if not (isinstance(explanation, str) and explanation.strip()):
            return {
                **state,
                "error": "Quiz validation failed: explanation is missing or empty.",
            }

        # No duplicate question_text.
        if question_text in seen_texts:
            return {
                **state,
                "error": "Quiz validation failed: duplicate question text.",
            }
        seen_texts.add(question_text)

    return {**state, "validated_questions": parsed}


async def persist_quiz_draft(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = _session(config)
    repo = QuizRepository(session)
    validated = state.get("validated_questions") or []

    quiz_id = await repo.create_quiz_draft_with_questions(
        node_id=state["node_id"],
        space_id=state["space_id"],  # type: ignore[arg-type]
        study_material_version_id=state["study_material_version_id"],  # type: ignore[arg-type]
        title=state.get("quiz_title") or "Quiz",
        difficulty=state["difficulty"],
        created_by=state["mentor_id"],
        questions=validated,
    )

    return {**state, "created_quiz_id": quiz_id}
